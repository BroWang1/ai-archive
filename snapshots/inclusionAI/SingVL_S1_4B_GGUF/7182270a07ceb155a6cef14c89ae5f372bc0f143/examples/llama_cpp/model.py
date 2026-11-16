"""Sing VL S1 protocol adapter over the unmodified llama.cpp CPU library."""
import ctypes as C
import hashlib
import json
import math
import os
import re
import threading
from pathlib import Path
import numpy as np
from transformers import AutoProcessor
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from processing.protocol import (MODEL_ID, PUBLIC_IMAGE_MAX_PIXELS, Unsupported, questions_for_state, render, resize_image, IMAGE_SLOT, decode_answer)
from processing import Processor

class SingVLS1(Processor):
    def __init__(self, model, device='cpu', image_max_pixels=PUBLIC_IMAGE_MAX_PIXELS):
        if device != 'cpu': raise ValueError('This adapter is CPU only')
        super().__init__(model, image_max_pixels)
        self.capacity=int(os.environ.get('JEV_CPU_CONTEXT','4096'))
        self.lib=C.CDLL(os.environ.get('JEV_RUNNER_LIBRARY', str(Path(__file__).with_name('libjev_runner.so'))))
        self.lib.jev_error.restype=C.c_char_p
        self.lib.jev_init.argtypes=[C.c_char_p,C.c_char_p,C.c_int,C.c_int];self.lib.jev_init.restype=C.c_void_p
        self.lib.jev_free.argtypes=[C.c_void_p]
        iptr=C.POINTER(C.c_int);bptr=C.POINTER(C.c_ubyte)
        self.lib.jev_run.argtypes=[C.c_void_p,C.c_char_p,C.POINTER(bptr),iptr,iptr,C.c_int,iptr,C.c_int,C.POINTER(C.c_float),iptr,C.c_int,C.c_int,iptr,iptr]
        self.lib.jev_run.restype=C.c_int
        self.ptr=self.lib.jev_init(os.environ['JEV_GGUF_MODEL'].encode(),os.environ['JEV_GGUF_MMPROJ'].encode(),self.capacity,int(os.environ.get('JEV_CPU_THREADS','8')))
        if not self.ptr:raise RuntimeError(self.lib.jev_error().decode())
        self.lock=threading.Lock()
    def close(self):
        if self.ptr:self.lib.jev_free(self.ptr);self.ptr=None
    def runtime(self):
        return {'backend':'unmodified llama.cpp CPU library','attention':'bidirectional full attention, causal GDN','decode_calls_per_question':1,'context_capacity':self.capacity}
    def predict(self,state,questions,images=()):
        with self.lock:return self._predict(state,questions,images)
    def _predict(self,state,questions,images):
        if len(images)>4:raise Unsupported('at most four images per request')
        requests=list(questions_for_state(state,questions,len(images)))
        features=self.encode_images(images)
        prepared=[np.asarray(resize_image(im,self.image_factor,self.min_pixels,self.image_max_pixels),dtype=np.uint8).copy() for im in images]
        if any('<__media__>' in str(x) for x in [state,questions]):raise Unsupported('reserved backend media marker')
        answers={};details={}
        for qid,kind,st,ins,options in requests:
            prompt=render(st,ins,options,self.labels)
            batch,ids=self.encode(prompt,features)
            if len(ids)>self.capacity:raise Unsupported(f'CPU validation capacity is {self.capacity}; got {len(ids)}')
            for code,tid in zip(self.labels[:len(options)],self.choice_ids):
                if self.tokenizer.encode(prompt+code,add_special_tokens=False)!=self.tokenizer.encode(prompt,add_special_tokens=False)+[tid]:raise ValueError('candidate is not one appended token')
            ni=len(prepared);nc=len(options);bptr=C.POINTER(C.c_ubyte)
            ptrs=(bptr*ni)(*[im.ctypes.data_as(bptr) for im in prepared]);ws=(C.c_int*ni)(*[im.shape[1] for im in prepared]);hs=(C.c_int*ni)(*[im.shape[0] for im in prepared])
            candidates=(C.c_int*nc)(*self.choice_ids[:nc]);out=(C.c_float*nc)();trace=(C.c_int*self.capacity)();counts=(C.c_int*ni)();positions=(C.c_int*(self.capacity*3))()
            n=self.lib.jev_run(self.ptr,prompt.replace(IMAGE_SLOT,'<__media__>').encode(),ptrs,ws,hs,ni,candidates,nc,out,trace,self.capacity,self.image_id,counts,positions)
            if n<0:raise RuntimeError(self.lib.jev_error().decode())
            if list(trace[:n])!=ids:raise ValueError(f'llama.cpp token sequence differs from reference: native={n}, reference={len(ids)}')
            answers[qid]=decode_answer(kind,options,list(out),questions[qid].get('criteria'))
            details[qid]={'input_tokens':n,'input_ids_sha256':hashlib.sha256(json.dumps([ids]).encode()).hexdigest(),'image_grid_thw':features['image_grid_thw'].tolist() if features else None,'image_tokens':sum(counts),'candidate_logits':list(out),'image_token_counts':list(counts),'positions':np.array(positions[:n*3]).reshape(n,3).T.tolist(),'decode_calls':1,'memory_cleared':True}
        return {'model':MODEL_ID,'answers':answers,'usage':{'input_tokens':sum(x['input_tokens'] for x in details.values()),'output_tokens':0}},details

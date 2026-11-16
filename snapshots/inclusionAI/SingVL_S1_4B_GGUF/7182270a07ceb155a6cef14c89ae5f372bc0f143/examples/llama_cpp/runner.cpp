#include "llama.h"
#include "mtmd.h"
#include "ggml-backend.h"
#include <vector>
#include <string>
#include <stdexcept>
#include <memory>
#include <cmath>
#include <algorithm>
struct Runner { llama_model *model=nullptr; llama_context *ctx=nullptr; mtmd_context *vision=nullptr; int capacity=0; ~Runner(){if(vision)mtmd_free(vision);if(ctx)llama_free(ctx);if(model)llama_model_free(model);} };
static thread_local std::string error;
static void require(bool ok,const char *msg){if(!ok)throw std::runtime_error(msg);}
extern "C" const char *jev_error(){return error.c_str();}
extern "C" void *jev_init(const char *model,const char *projector,int capacity,int threads){
 try {
  ggml_backend_load_all();llama_backend_init();auto r=std::make_unique<Runner>();r->capacity=capacity;
  auto mp=llama_model_default_params();mp.n_gpu_layers=0;
  r->model=llama_model_load_from_file(model,mp);require(r->model,"model load failed");
  auto cp=llama_context_default_params();cp.n_ctx=capacity;cp.n_batch=capacity;cp.n_ubatch=capacity;cp.n_seq_max=1;cp.n_outputs_max=1;cp.n_threads=threads;cp.n_threads_batch=threads;cp.flash_attn_type=LLAMA_FLASH_ATTN_TYPE_ENABLED;
  r->ctx=llama_init_from_model(r->model,cp);require(r->ctx,"context load failed");
  require(!llama_get_causal_attn(r->ctx),"GGUF must declare non-causal attention");
  auto vp=mtmd_context_params_default();vp.use_gpu=false;vp.n_threads=threads;vp.warmup=false;vp.image_min_tokens=64;vp.image_max_tokens=1600;
  r->vision=mtmd_init_from_file(projector,r->model,vp);require(r->vision,"projector load failed");
  return r.release();
 } catch(const std::exception &e){error=e.what();return nullptr;}
}
extern "C" void jev_free(void *ptr){delete static_cast<Runner*>(ptr);}
extern "C" int jev_run(void *ptr,const char *prompt,const unsigned char **rgb,const int *width,const int *height,int ni,const int *candidates,int nc,float *logits,int *trace,int trace_size,int image_id,int *image_counts,int *positions){
 try {
  auto &r=*static_cast<Runner*>(ptr);error.clear();llama_memory_clear(llama_get_memory(r.ctx),true);
  std::vector<std::unique_ptr<mtmd_bitmap,decltype(&mtmd_bitmap_free)>> owned;
  std::vector<const mtmd_bitmap*> bitmaps;
  for(int i=0;i<ni;i++){owned.emplace_back(mtmd_bitmap_init(width[i],height[i],rgb[i]),mtmd_bitmap_free);require(bool(owned.back()),"bitmap failed");bitmaps.push_back(owned.back().get());}
  auto chunks=std::unique_ptr<mtmd_input_chunks,decltype(&mtmd_input_chunks_free)>(mtmd_input_chunks_init(),mtmd_input_chunks_free);
  mtmd_input_text text{prompt,std::char_traits<char>::length(prompt),false,true};
  require(mtmd_tokenize(r.vision,chunks.get(),&text,bitmaps.data(),bitmaps.size())==0,"mtmd tokenize failed");
  size_t total=0;for(size_t i=0;i<mtmd_input_chunks_size(chunks.get());i++)total+=mtmd_input_chunk_get_n_tokens(mtmd_input_chunks_get(chunks.get(),i));
  require(total>0 && total<=size_t(r.capacity) && total<=size_t(trace_size),"prompt exceeds batch capacity");
  auto batch=std::unique_ptr<llama_batch_ext,decltype(&llama_batch_ext_free)>(llama_batch_ext_init(r.ctx),llama_batch_ext_free);
  std::vector<std::vector<float>> embeddings;int offset=0,image_index=0,last=-1;llama_pos pos=0;
  int dim=llama_model_n_embd_inp(r.model);
  for(size_t ci=0;ci<mtmd_input_chunks_size(chunks.get());ci++){
   auto chunk=mtmd_input_chunks_get(chunks.get(),ci);
   if(mtmd_input_chunk_get_type(chunk)==MTMD_INPUT_CHUNK_TYPE_TEXT){
    size_t nt=0;auto ids=mtmd_input_chunk_get_tokens_text(chunk,&nt);
    for(size_t j=0;j<nt;j++){
     last=llama_batch_ext_add_token(batch.get(),0,ids[j]);require(last>=0,"add token failed");
     require(llama_batch_ext_set_pos(batch.get(),last,&pos),"set text position failed");
     trace[offset]=ids[j];for(int k=0;k<3;k++)positions[offset*3+k]=pos;offset++;pos++;
    }
   } else {
    require(mtmd_input_chunk_get_type(chunk)==MTMD_INPUT_CHUNK_TYPE_IMAGE,"only images supported");
    require(mtmd_encode_chunk(r.vision,chunk)==0,"vision encode failed");
    size_t nt=mtmd_input_chunk_get_n_tokens(chunk);auto data=mtmd_get_output_embd(r.vision);require(data,"missing embeddings");
    embeddings.emplace_back(data,data+nt*dim);auto &values=embeddings.back();
    require(image_index<ni,"unexpected image chunks");image_counts[image_index++]=nt;
    auto image=mtmd_input_chunk_get_tokens_image(chunk);
    for(size_t j=0;j<nt;j++){
     llama_embd emb{values.data()+j*dim,1,size_t(dim)};
     last=llama_batch_ext_add_embd(batch.get(),0,emb);require(last>=0,"add image embedding failed");
     auto p=mtmd_image_tokens_get_decoder_pos(image,pos,j);llama_pos coords[4]={llama_pos(p.t),llama_pos(p.y),llama_pos(p.x),llama_pos(p.z)};
     require(llama_batch_ext_set_pos(batch.get(),last,coords),"set image position failed");
     trace[offset]=image_id;for(int k=0;k<3;k++)positions[offset*3+k]=coords[k];offset++;
    }
    pos+=mtmd_input_chunk_get_n_pos(chunk);
   }
  }
  require(image_index==ni,"image count mismatch");require(llama_batch_ext_set_output_logits(batch.get(),last,true),"output selection failed");
  require(llama_process(r.ctx,LLAMA_PROCESS_TYPE_DECODE,batch.get())==0,"model forward failed");
  auto out=llama_get_logits_ith(r.ctx,-1);require(out,"missing logits");
  int nv=llama_vocab_n_tokens(llama_model_get_vocab(r.model));
  for(int i=0;i<nc;i++){require(candidates[i]>=0&&candidates[i]<nv,"invalid candidate id");logits[i]=out[candidates[i]];require(std::isfinite(logits[i]),"nonfinite logits");}
  return offset;
 }catch(const std::exception &e){error=e.what();return -1;}
}

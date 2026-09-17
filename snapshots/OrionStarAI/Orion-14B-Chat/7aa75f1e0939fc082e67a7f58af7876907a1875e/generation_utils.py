from typing import List
from queue import Queue

# build chat input prompt
def build_chat_input(tokenizer, messages: List[dict]):
    # chat format:
    # single-turn: <s>Human: Hello!\n\nAssistant: </s>
    # multi-turn:  <s>Human: Hello!\n\nAssistant: </s>Hi!</s>Human: How are you?\n\nAssistant: </s>I'm fine</s>

    prompt = "<s>"
    for msg in messages:
        role = msg["role"]
        message = msg["content"]
        if message is None :
            continue
        if role == "user":
            prompt += "Human: " + message + "\n\nAssistant: </s>"
        if role == "assistant":
            prompt += message + "</s>"

    input_tokens = tokenizer.encode(prompt)
    return input_tokens


class TextIterStreamer:
    def __init__(self, tokenizer, skip_prompt=False, skip_special_tokens=False):
        self.tokenizer = tokenizer
        self.skip_prompt = skip_prompt
        self.skip_special_tokens = skip_special_tokens
        self.tokens = []
        self.text_queue = Queue()
        self.next_tokens_are_prompt = True

    def put(self, value):
        if self.skip_prompt and self.next_tokens_are_prompt:
            self.next_tokens_are_prompt = False
        else:
            if len(value.shape) > 1:
                value = value[0]
            self.tokens.extend(value.tolist())
            self.text_queue.put(
                self.tokenizer.decode(self.tokens, skip_special_tokens=self.skip_special_tokens))

    def end(self):
        self.text_queue.put(None)

    def __iter__(self):
        return self

    def __next__(self):
        value = self.text_queue.get()
        if value is None:
            raise StopIteration()
        else:
            return value


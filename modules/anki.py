from os import walk
from mistralai import Mistral
import time
import json


class JarMick():

  def __init__(self, config, callLLM) -> None:

    self.triage = {
      "name": "anki",
      "description": "Anki is a flashcard program. It uses cards. It uses technics from cognitive science such as active recall testing and spaced repetition to help me in my memorization. I use Anki to train myself on memorizing and reinforcing my knowledge.",
      "consigne": 'If the request is about Anki or what services Anki provides to me (memorizing or training my knowledge), the "service" field is set to "anki".'
    }

    self.conf = config
    self.callLLM = callLLM

  def request(self, user):
    time.sleep(1.5)




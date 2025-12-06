from enum import Enum
from os import getenv


class SFX(Enum):
	CORRECT = getenv("SFX_QUIZ_CORRECT")
	INCORRECT = getenv("SFX_QUIZ_INCORRECT")
	Q = getenv("SFX_QUIZ_Q")
	A = getenv("SFX_QUIZ_A")

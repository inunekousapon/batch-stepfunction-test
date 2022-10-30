import random

choice = random.choice([True, False])

if choice:
    print("hello world")
else:
    raise Exception("error occur.")

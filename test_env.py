import os
from dotenv import load_dotenv

with open('.env', 'w') as f:
    f.write('ACCESS_TOKEN_EXPIRE_MINUTES=43200\n')

print("Before:", os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))
load_dotenv()
print("After:", os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))

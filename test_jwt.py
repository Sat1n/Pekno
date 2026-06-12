import os
import jwt
from datetime import datetime, timezone, timedelta
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "43200"
EXPIRE = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))
expire = datetime.now(timezone.utc) + timedelta(minutes=EXPIRE)
token = jwt.encode({"exp": expire, "sub": "test"}, "secret", algorithm="HS256")
payload = jwt.decode(token, "secret", algorithms=["HS256"])
print("Decoded:", payload)

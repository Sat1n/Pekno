from jose import jwt
from datetime import datetime, timezone, timedelta
import json
import base64

expire = datetime.now(timezone.utc) + timedelta(minutes=120)
token = jwt.encode({"exp": expire, "sub": "test"}, "secret", algorithm="HS256")
parts = token.split(".")
print(base64.urlsafe_b64decode(parts[1] + "=="))

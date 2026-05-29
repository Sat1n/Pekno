from jose import jwt
from datetime import datetime, timezone, timedelta
expire = datetime.now(timezone.utc) + timedelta(minutes=120)
token = jwt.encode({"exp": expire}, "secret", algorithm="HS256")
payload = jwt.decode(token, "secret", algorithms=["HS256"])
print("Decoded:", payload)

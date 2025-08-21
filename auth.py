import firebase_admin
from firebase_admin import auth, credentials
from fastapi import HTTPException, status

# TODO: Set the GOOGLE_APPLICATION_CREDENTIALS environment variable
# to the path of your Firebase service account key file.
cred = credentials.ApplicationDefault()
firebase_admin.initialize_app(cred)

async def verify_token(token: str):
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        decoded_token = auth.verify_id_token(token)
        email = decoded_token.get("email")
        if not email or not email.endswith("@google.com"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User not allowed",
            )
        return decoded_token
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {e}",
        )

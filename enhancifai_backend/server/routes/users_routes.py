
import os
import re
import time
from fastapi import APIRouter, Depends, HTTPException, Request, status, Form


from typing import Optional

from fastapi.responses import JSONResponse
from enhancifai_backend.database.handlers.users import UsersDbCore, UsersDbLoginTokens, UsersDbPswdResetTokens, UsersDbRegisterTokens
from enhancifai_backend.integrations.sendgrid_api import SendGrid
from enhancifai_backend.server.models.users import Password, PasswordReset, Profile, UserCreatePassword, UserLoginPassword, UserPasswordReset, ValidateRegister
from enhancifai_backend.oauth.google import google_auth
from enhancifai_backend.server.utils import clean_user_data, create_jwt_token, generate_unique_token, get_current_user_id, hash_password, verify_secret_key

router = APIRouter()

@router.post("/users/profile/", tags=["Users"])
async def update_user_profile(profile: Profile, user_id: int = Depends(get_current_user_id), _api_key: str = Depends(verify_secret_key)):
    try:
        UsersDbCore.update_user_profile(
            user_id=user_id, 
            name=profile.name,
        )
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        # Catch-all for unexpected errors
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})
    return JSONResponse(status_code=200, content={"message": "Profile updated successfully."})


@router.get("/users/profile/", tags=["Users"])
async def get_user_profile(user_id: int = Depends(get_current_user_id), _api_key: str = Depends(verify_secret_key)):
    try:
        user_details = UsersDbCore.get_user_by_id(user_id)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        # Catch-all for unexpected errors
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})
    return JSONResponse(status_code=200, content=clean_user_data(user_details))

@router.post("/users/password/update", tags=["Users"])
async def update_password(password: Password, user_id: int = Depends(get_current_user_id), _api_key: str = Depends(verify_secret_key)):
    try:
        user = UsersDbCore.get_user_by_id(user_id)
        email = user['email']
        if password.old_password == "":
            old = True
        else:
            old_hash = hash_password(password.old_password)
            old = UsersDbCore.check_user_password(email, old_hash)
        if old is False:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Old password is incorrect.")
        else:
            new_hash = hash_password(password.new_password)
            UsersDbCore.set_user_password(user_id, new_hash)
            result = {
                "message": "User password has been updated successfully."
            }
            return JSONResponse(status_code=200, content=result)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        # Catch-all for unexpected errors
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})

@router.post("/users/password/forgot", tags=["Users"])
async def forgot_password(user: UserPasswordReset, _api_key: str = Depends(verify_secret_key)):
    try:
        if '@' not in user.email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format.")
        # check if user exists
        exists = UsersDbCore.get_user_by_email(user.email) is not None
        if exists is False:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User does not exist.")
        token = generate_unique_token()
        UsersDbPswdResetTokens.create_user_password_reset_token(user.email, token)
        SendGrid.send_password_reset_email(user.email, token)
        result = {
            "message": "User password reset email sent successfully."
        }
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        # Catch-all for unexpected errors
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})
    return JSONResponse(status_code=200, content=result)

@router.post("/users/password/reset", tags=["Users"])
async def reset_password(password: PasswordReset, _api_key: str = Depends(verify_secret_key)):
    try:
        token_email = UsersDbPswdResetTokens.get_email_from_password_reset_token(password.token)
        if token_email is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid reset token.")
        # all checks pass, password can change
        email = token_email['email']
        user = UsersDbCore.get_user_by_email(email)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User does not exist for reset token.")
        new_hash = hash_password(password.new_password)
        UsersDbCore.set_user_password(user['user_id'], new_hash)
        result = {
            "message": "User password has been reset successfully."
        }
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        # Catch-all for unexpected errors
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})
    return JSONResponse(status_code=200, content=result)

@router.get("/users/register/google", tags=["Users"])
async def create_user_google(_api_key: str = Depends(verify_secret_key)):
    try:
        url = google_auth.authenticate_url()
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        # Catch-all for unexpected errors
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})
    return JSONResponse(status_code=200, content=url)

@router.post("/users/register/", tags=["Users"])
async def create_user(user: UserCreatePassword, _api_key: str = Depends(verify_secret_key)):
    try:
        # Validate email
        if not re.match(r"[^@]+@[^@]+\.[^@]+", user.email):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid email format')

        # check if user exists
        exists = UsersDbCore.get_user_by_email(user.email) is not None
        if exists:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This email is already registered, please login instead.")

        # Validate password
        if len(user.password) < 8:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Password must be at least 8 characters long')

        user_reg_token = generate_unique_token()
        password_hash = hash_password(user.password)
        UsersDbRegisterTokens.create_user_register_token(user.email, user_reg_token)
        UsersDbCore.create_user_by_email(user.email,user.name, password_hash)
        SendGrid.send_registration_email(user.email, user_reg_token, user.name)
        
        login_token, login_expiration = create_jwt_token({"email": user.email})
        result = {
            "message": "User registration email sent successfully.",
            "token": login_token,
            "expiration": login_expiration
        }
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        # Catch-all for unexpected errors
        return JSONResponse(status_code=500, content={"detail": str(e), "error": str(e)})
    return JSONResponse(status_code=200, content=result)

@router.post("/validate/register", tags=["Users"])
async def validate_register_token(req_validate: ValidateRegister):
    try:
        exists = UsersDbRegisterTokens.check_user_register_token(req_validate.email, req_validate.token)
        if exists is False:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token.")
        UsersDbRegisterTokens.redeem_user_register_token(req_validate.email, req_validate.token)
        UsersDbCore.verify_email(req_validate.email)
        token, expiration = create_jwt_token({"email": req_validate.email})
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        # Catch-all for unexpected errors
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})
    return JSONResponse(status_code=200, content={"token": token, "expiration": expiration})

@router.get("/auth/google/callback", tags=["Users"])
async def google_callback(code: str, state: str, _api_key: str = Depends(verify_secret_key)):
    try:
        user_info = google_auth.fetch_token(code, state=state)
        user_email = user_info['email']
        user_details = UsersDbCore.get_user_by_email(user_email)
        timestamp = time.time()
        if user_details is None:
            # create new user
            user_id = UsersDbCore.create_user_by_email(user_email,name="")
        else:
            # update existing user
            user_id = user_details['user_id']
            UsersDbCore.update_google_login(
                user_id=user_id,
                google_oauth_token=timestamp
            )
        new_token, expiration = create_jwt_token({"email": user_email}, days=7)
        result = {
            "email": user_email,
            "token": new_token,
            "expiration": expiration
        }
        SendGrid.send_social_account_ready_email(user_email, f"{os.getenv('FRONTEND_URL')}/login")
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        # Catch-all for unexpected errors
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})
    return JSONResponse(status_code=200, content=result)

@router.post("/users/login/password", tags=["Users"])
async def login_password(user: UserLoginPassword, _api_key: str = Depends(verify_secret_key)):
    try:
        exists = UsersDbCore.get_user_by_email(user.email)
        if not exists:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User does not exist.")
        # check password
        password_hash = hash_password(user.password)
        valid = UsersDbCore.check_user_password(user.email, password_hash)
        if valid is not True:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password is not correct.")
        token, expiration = create_jwt_token({"email": user.email})
        result = {
            "message": "Login successful.",
            "token": token,
            "expiration": expiration
        }
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        # Catch-all for unexpected errors
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})
    return JSONResponse(status_code=200, content=result)

@router.get("/validate/password_reset", tags=["Users"])
async def validate_password_reset_token(token: str, email: str):
    exists = UsersDbPswdResetTokens.check_user_password_reset_token(email=email, token=token)
    return JSONResponse(content={"exists": exists})

@router.get("/users/consent/ai", tags=["Users"])
async def check_user_ai_consent(user_id: int = Depends(get_current_user_id), _api_key: str = Depends(verify_secret_key)):
    """
    Check if the current user has given consent for AI usage.

    Returns:
        JSONResponse: 
            A JSON response containing the user's AI consent status.
            Example response:
            {
                "consent": bool
            }
    """
    consent = UsersDbCore.check_ai_consent(user_id)
    return JSONResponse(content={"consent": consent})

@router.post("/users/consent/ai", tags=["Users"])
async def update_user_ai_consent(user_id: int = Depends(get_current_user_id), _api_key: str = Depends(verify_secret_key)):
    """
    Update the AI consent status for the current user.

    Returns:
        JSONResponse: 
            A JSON response indicating that the AI consent was updated successfully.
            Example response:
            {
                "message": "AI consent updated successfully."
            }
    """
    UsersDbCore.update_ai_consent(user_id)
    return JSONResponse(content={"message": "AI consent updated successfully."})
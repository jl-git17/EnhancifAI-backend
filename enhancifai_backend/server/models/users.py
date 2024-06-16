from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, constr, validator
from datetime import date
from enum import Enum

class UserCreatePassword(BaseModel):
    email: str
    password: str
    name: str

class UserPasswordReset(BaseModel):
    email: EmailStr

class UserLoginApple(BaseModel):
    code: str

class UserLoginPassword(BaseModel):
    email: EmailStr
    password: str

class Profile(BaseModel):
    email: str
    name: Optional[str] = ""

class Password(BaseModel):
    old_password: str
    new_password: str

class PasswordReset(BaseModel):
    token: str
    new_password: str

class ValidateRegister(BaseModel):
    email: str
    token: str
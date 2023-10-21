from pydantic import BaseModel


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str

    def dict(self, **kwargs):
        token_dict = super().dict(**kwargs)
        token_dict["access_token"] = f"Bearer {token_dict['access_token']}"
        token_dict["refresh_token"] = self.refresh_token
        return token_dict


class VerificationResponse(BaseModel):
    verification_code: str


class CheckCodeResponse(BaseModel):
    message: str

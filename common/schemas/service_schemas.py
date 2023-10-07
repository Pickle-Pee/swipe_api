from pydantic import BaseModel


class CityQuery(BaseModel):
    query: str

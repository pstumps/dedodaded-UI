from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dedodaded.game_specs import Game


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginRequest(RequestModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class CreateServerRequest(RequestModel):
    game: Game
    name: str = Field(min_length=3, max_length=64)
    world_name: str = Field(min_length=1, max_length=64)
    password: str = Field(max_length=64)
    admin_password: str = Field(default="", max_length=64)
    port: int = Field(ge=1024, le=65533)
    max_players: int = Field(ge=1, le=100)
    public: bool = True

    @field_validator("name", "world_name")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(ord(character) < 32 for character in value):
            raise ValueError("Control characters are not allowed")
        return value

    @model_validator(mode="after")
    def validate_game_settings(self) -> CreateServerRequest:
        if self.game is Game.VALHEIM:
            if len(self.password) < 5:
                raise ValueError("Valheim passwords must contain at least 5 characters")
            if self.max_players > 10:
                raise ValueError("Valheim supports at most 10 players")
        if self.game is Game.PROJECT_ZOMBOID and (
            len(self.admin_password) < 8 or not self.admin_password.isalnum()
        ):
            raise ValueError(
                "Project Zomboid admin passwords must contain at least 8 letters or digits"
            )
        return self


class WorkshopLookupRequest(RequestModel):
    workshop_id: str = Field(min_length=1, max_length=32, pattern=r"^[0-9]+$")


class ZomboidModRequest(WorkshopLookupRequest):
    name: str = Field(min_length=1, max_length=120)
    mod_id: str = Field(min_length=1, max_length=160)

    @field_validator("mod_id")
    @classmethod
    def validate_mod_id(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
            raise ValueError("The internal mod ID contains unsupported characters")
        return value


class ValheimModRequest(RequestModel):
    package_id: str = Field(min_length=3, max_length=180, pattern=r"^[A-Za-z0-9_.-]+$")

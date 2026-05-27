from datetime import datetime

from pydantic import BaseModel, Field


class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=120, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    name: str
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TeamResponse(BaseModel):
    id: int
    name: str
    code: str
    group_name: str | None

    class Config:
        from_attributes = True


class MatchResponse(BaseModel):
    id: int
    stage: str
    group_name: str | None
    team_a_id: int
    team_b_id: int
    team_a_name: str | None = None
    team_b_name: str | None = None
    team_a_code: str | None = None
    team_b_code: str | None = None
    real_score_a: int | None
    real_score_b: int | None
    status: str
    bracket_slot: str | None
    match_order: int

    class Config:
        from_attributes = True


class MatchCreate(BaseModel):
    stage: str
    group_name: str | None = None
    team_a_id: int
    team_b_id: int
    bracket_slot: str | None = None
    match_order: int = 0


class MatchUpdate(BaseModel):
    real_score_a: int | None = None
    real_score_b: int | None = None
    status: str | None = None
    team_a_id: int | None = None
    team_b_id: int | None = None


class PredictionCreate(BaseModel):
    match_id: int
    predicted_score_a: int = Field(ge=0)
    predicted_score_b: int = Field(ge=0)


from pydantic import BaseModel, EmailStr, Field


class KnockoutPredictionCreate(BaseModel):
    bracket_slot: str
    stage: str
    sim_team_a_id: int | None = None
    sim_team_b_id: int | None = None
    predicted_score_a: int = Field(ge=0)
    predicted_score_b: int = Field(ge=0)


class PredictionBulkSubmit(BaseModel):
    predictions: list[PredictionCreate]
    knockout_predictions: list[KnockoutPredictionCreate] = []
    top_scorer: str | None = None
    top_assister: str | None = None


class PredictionResponse(BaseModel):
    id: int
    match_id: int
    predicted_score_a: int
    predicted_score_b: int

    class Config:
        from_attributes = True


class LeaderboardEntry(BaseModel):
    user_id: int
    name: str
    username: str | None = None
    total_score: float
    group_score: float
    knockout_score: float
    special_score: float
    rank: int
    rank_change: int | None = None
    daily_points: float | None = None


class UserScoreResponse(BaseModel):
    user_id: int
    name: str
    group_score: int
    qualification_score: int
    knockout_score: int
    special_score: int
    chain_bonus: float
    total_score: float
    breakdown_json: dict | None

    class Config:
        from_attributes = True


class TournamentSettingsResponse(BaseModel):
    predictions_locked: bool
    tournament_started: bool
    actual_top_scorer: str | None
    actual_top_assister: str | None


class TournamentSettingsUpdate(BaseModel):
    predictions_locked: bool | None = None
    tournament_started: bool | None = None
    actual_top_scorer: str | None = None
    actual_top_assister: str | None = None


class TournamentImportRequest(BaseModel):
    slug: str = "worldcup_2026"
    reset: bool = False
    set_active: bool = True


class GroupStandingsResponse(BaseModel):
    group_name: str
    standings: list[dict]
    qualified_teams: list[dict]

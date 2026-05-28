import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MatchStage(str, enum.Enum):
    GROUP = "group"
    R32 = "R32"
    R16 = "R16"
    QF = "QF"
    SF = "SF"
    F = "F"


class MatchStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"


class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    format_type: Mapped[str] = mapped_column(String(50), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    format_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    groups: Mapped[list["Group"]] = relationship(back_populates="tournament")
    teams: Mapped[list["Team"]] = relationship(back_populates="tournament")
    matches: Mapped[list["Match"]] = relationship(back_populates="tournament")
    settings: Mapped["TournamentSettings | None"] = relationship(back_populates="tournament", uselist=False)


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (UniqueConstraint("tournament_id", "name", name="uq_tournament_group"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(2), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)

    tournament: Mapped["Tournament"] = relationship(back_populates="groups")
    teams: Mapped[list["Team"]] = relationship(back_populates="group")


class Stadium(Base):
    __tablename__ = "stadiums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    country: Mapped[str] = mapped_column(String(120), nullable=False)
    timezone: Mapped[str] = mapped_column(String(60), default="UTC")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    predictions: Mapped[list["Prediction"]] = relationship(back_populates="user")
    special_prediction: Mapped["SpecialPrediction | None"] = relationship(back_populates="user", uselist=False)
    score: Mapped["UserScore | None"] = relationship(back_populates="user", uselist=False)
    match_scores: Mapped[list["UserMatchScore"]] = relationship(back_populates="user")
    knockout_bracket: Mapped[list["UserKnockoutBracket"]] = relationship(back_populates="user")
    standings_cache: Mapped[list["GroupStandingsCache"]] = relationship(back_populates="user")


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("tournament_id", "code", name="uq_tournament_team_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int | None] = mapped_column(ForeignKey("tournaments.id"), nullable=True, index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    group_name: Mapped[str | None] = mapped_column(String(2), nullable=True)
    flag_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    confederation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    group_position: Mapped[int | None] = mapped_column(Integer, nullable=True)

    tournament: Mapped["Tournament | None"] = relationship(back_populates="teams")
    group: Mapped["Group | None"] = relationship(back_populates="teams")
    group_matches_a: Mapped[list["Match"]] = relationship(
        back_populates="team_a", foreign_keys="Match.team_a_id"
    )
    group_matches_b: Mapped[list["Match"]] = relationship(
        back_populates="team_b", foreign_keys="Match.team_b_id"
    )


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int | None] = mapped_column(ForeignKey("tournaments.id"), nullable=True, index=True)
    stage: Mapped[MatchStage] = mapped_column(Enum(MatchStage), nullable=False, index=True)
    group_name: Mapped[str | None] = mapped_column(String(2), nullable=True)
    team_a_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    team_b_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    stadium_id: Mapped[int | None] = mapped_column(ForeignKey("stadiums.id"), nullable=True)
    kickoff_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    match_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    matchday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage_order: Mapped[int] = mapped_column(Integer, default=0)
    real_score_a: Mapped[int | None] = mapped_column(Integer, nullable=True)
    real_score_b: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[MatchStatus] = mapped_column(Enum(MatchStatus), default=MatchStatus.SCHEDULED)
    bracket_slot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    knockout_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), nullable=True)
    next_match_slot: Mapped[str | None] = mapped_column(String(1), nullable=True)
    match_order: Mapped[int] = mapped_column(Integer, default=0)
    feeder_a_match_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feeder_b_match_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    tournament: Mapped["Tournament | None"] = relationship(back_populates="matches")
    stadium: Mapped["Stadium | None"] = relationship()
    team_a: Mapped["Team"] = relationship(foreign_keys=[team_a_id], back_populates="group_matches_a")
    team_b: Mapped["Team"] = relationship(foreign_keys=[team_b_id], back_populates="group_matches_b")
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="match")
    user_match_scores: Mapped[list["UserMatchScore"]] = relationship(back_populates="match")


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (UniqueConstraint("user_id", "match_id", name="uq_user_match_prediction"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), nullable=False, index=True)
    predicted_score_a: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_score_b: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped["User"] = relationship(back_populates="predictions")
    match: Mapped["Match"] = relationship(back_populates="predictions")


class UserMatchScore(Base):
    """Per-match points ledger — idempotent; one row per user per match."""

    __tablename__ = "user_match_scores"
    __table_args__ = (UniqueConstraint("user_id", "match_id", name="uq_user_match_score"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), nullable=False, index=True)
    points_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    breakdown_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="match_scores")
    match: Mapped["Match"] = relationship(back_populates="user_match_scores")


class SpecialPrediction(Base):
    __tablename__ = "special_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    top_scorer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    top_assister: Mapped[str | None] = mapped_column(String(120), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="special_prediction")


class GroupStandingsCache(Base):
    __tablename__ = "group_standings_cache"
    __table_args__ = (UniqueConstraint("user_id", "group_name", name="uq_user_group_cache"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    group_name: Mapped[str] = mapped_column(String(2), nullable=False)
    standings_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    qualified_teams: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="standings_cache")


class UserScore(Base):
    __tablename__ = "user_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    group_score: Mapped[int] = mapped_column(Integer, default=0)
    qualification_score: Mapped[int] = mapped_column(Integer, default=0)
    knockout_score: Mapped[int] = mapped_column(Integer, default=0)
    special_score: Mapped[int] = mapped_column(Integer, default=0)
    chain_bonus: Mapped[float] = mapped_column(Float, default=0.0)
    total_score: Mapped[float] = mapped_column(Float, default=0.0)
    breakdown_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="score")


class LeaderboardSnapshot(Base):
    __tablename__ = "leaderboard_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    rankings_json: Mapped[list] = mapped_column(JSONB, nullable=False)


class TournamentSettings(Base):
    __tablename__ = "tournament_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int | None] = mapped_column(ForeignKey("tournaments.id"), nullable=True, unique=True)
    predictions_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    tournament_started: Mapped[bool] = mapped_column(Boolean, default=False)
    actual_top_scorer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actual_top_assister: Mapped[str | None] = mapped_column(String(120), nullable=True)
    knockout_rules_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tournament: Mapped["Tournament | None"] = relationship(back_populates="settings")


class KnockoutBracketCache(Base):
    __tablename__ = "knockout_bracket_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    stage: Mapped[MatchStage] = mapped_column(Enum(MatchStage), nullable=False)
    bracket_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "stage", name="uq_user_knockout_stage"),)


class KnockoutPrediction(Base):
    __tablename__ = "knockout_predictions"
    __table_args__ = (UniqueConstraint("user_id", "bracket_slot", name="uq_user_bracket_slot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    bracket_slot: Mapped[str] = mapped_column(String(20), nullable=False)
    stage: Mapped[MatchStage] = mapped_column(Enum(MatchStage), nullable=False)
    sim_team_a_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    sim_team_b_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    predicted_score_a: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_score_b: Mapped[int] = mapped_column(Integer, nullable=False)


class UserKnockoutBracket(Base):
    """Resolved per-user knockout fixture (matches 73–104) — no TBD after submit."""

    __tablename__ = "user_knockout_brackets"
    __table_args__ = (UniqueConstraint("user_id", "bracket_slot", name="uq_user_knockout_bracket_slot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), nullable=True, index=True)
    bracket_slot: Mapped[str] = mapped_column(String(20), nullable=False)
    stage: Mapped[MatchStage] = mapped_column(Enum(MatchStage), nullable=False, index=True)
    match_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    team_a_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    team_b_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    predicted_score_a: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    predicted_score_b: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_group_state_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="knockout_bracket")

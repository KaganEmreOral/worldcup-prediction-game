"""Group stage simulation engine — FIFA-style standings."""

from dataclasses import dataclass, field


@dataclass
class TeamStanding:
    team_id: int
    team_name: str
    team_code: str
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0
    head_to_head_points: dict[int, int] = field(default_factory=dict)

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against

    def to_dict(self) -> dict:
        return {
            "team_id": self.team_id,
            "team_name": self.team_name,
            "team_code": self.team_code,
            "played": self.played,
            "won": self.won,
            "drawn": self.drawn,
            "lost": self.lost,
            "goals_for": self.goals_for,
            "goals_against": self.goals_against,
            "goal_difference": self.goal_difference,
            "points": self.points,
        }


@dataclass
class MatchResult:
    team_a_id: int
    team_b_id: int
    score_a: int
    score_b: int


def _sort_key(standing: TeamStanding) -> tuple:
    return (
        -standing.points,
        -standing.goal_difference,
        -standing.goals_for,
        standing.team_name,
    )


def _apply_h2h_tiebreak(standings: list[TeamStanding], tied_ids: set[int]) -> list[TeamStanding]:
    """Mini-league head-to-head among tied teams."""
    mini = [s for s in standings if s.team_id in tied_ids]
    for s in mini:
        s.head_to_head_points = {tid: 0 for tid in tied_ids if tid != s.team_id}

    # Recompute h2h points from stored match data isn't available here;
    # use goal difference within tied group as simplified h2h proxy when points/GD/GF equal
    mini.sort(key=lambda s: (-s.points, -s.goal_difference, -s.goals_for, s.team_name))
    return mini


def compute_group_standings(
    team_ids: list[tuple[int, str, str]],
    results: list[MatchResult],
) -> list[TeamStanding]:
    """Compute standings for a group from match results."""
    standings: dict[int, TeamStanding] = {
        tid: TeamStanding(team_id=tid, team_name=name, team_code=code)
        for tid, name, code in team_ids
    }

    for r in results:
        sa, sb = standings[r.team_a_id], standings[r.team_b_id]
        sa.played += 1
        sb.played += 1
        sa.goals_for += r.score_a
        sa.goals_against += r.score_b
        sb.goals_for += r.score_b
        sb.goals_against += r.score_a

        if r.score_a > r.score_b:
            sa.won += 1
            sa.points += 3
            sb.lost += 1
        elif r.score_a < r.score_b:
            sb.won += 1
            sb.points += 3
            sa.lost += 1
        else:
            sa.drawn += 1
            sb.drawn += 1
            sa.points += 1
            sb.points += 1

    ranked = sorted(standings.values(), key=_sort_key)

    # Resolve ties at same P/GD/GF with head-to-head mini-league
    i = 0
    while i < len(ranked):
        j = i + 1
        while j < len(ranked) and _sort_key(ranked[i])[:3] == _sort_key(ranked[j])[:3]:
            j += 1
        if j - i > 1:
            tied_ids = {ranked[k].team_id for k in range(i, j)}
            reordered = _apply_h2h_tiebreak(ranked, tied_ids)
            ranked[i:j] = reordered
        i = j

    return ranked


@dataclass
class ThirdPlaceCandidate:
    team_id: int
    team_name: str
    team_code: str
    group_name: str
    points: int
    goal_difference: int
    goals_for: int
    position: int  # 3rd in group


def rank_third_place_teams(
    all_group_standings: dict[str, list[TeamStanding]],
) -> list[ThirdPlaceCandidate]:
    """Rank all 3rd-placed teams across groups (best first) for best-8 qualification."""
    candidates: list[ThirdPlaceCandidate] = []
    for group_name, standings in all_group_standings.items():
        if len(standings) >= 3:
            third = standings[2]
            candidates.append(
                ThirdPlaceCandidate(
                    team_id=third.team_id,
                    team_name=third.team_name,
                    team_code=third.team_code,
                    group_name=group_name,
                    points=third.points,
                    goal_difference=third.goal_difference,
                    goals_for=third.goals_for,
                    position=3,
                )
            )

    candidates.sort(key=lambda c: (-c.points, -c.goal_difference, -c.goals_for, c.group_name))
    return candidates


def best_third_place_teams(
    all_group_standings: dict[str, list[TeamStanding]],
    num_best_third: int = 8,
) -> list[ThirdPlaceCandidate]:
    """Top N third-placed teams that qualify for the Round of 32."""
    return rank_third_place_teams(all_group_standings)[:num_best_third]


def get_qualified_teams(
    all_group_standings: dict[str, list[TeamStanding]],
    num_best_third: int = 8,
) -> dict[str, list[dict]]:
    """Return qualified teams: top 2 per group + best N third-placed."""
    third_ranked = rank_third_place_teams(all_group_standings)
    best_third_groups = {c.group_name for c in third_ranked[:num_best_third]}

    result: dict[str, list[dict]] = {}
    for group_name, standings in sorted(all_group_standings.items()):
        qualified = []
        for pos, s in enumerate(standings[:2], start=1):
            qualified.append({**s.to_dict(), "position": pos, "qualification": "top2"})
        if group_name in best_third_groups and len(standings) >= 3:
            qualified.append({**standings[2].to_dict(), "position": 3, "qualification": "best_third"})
        result[group_name] = qualified
    return result

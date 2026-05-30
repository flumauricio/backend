from pydantic import BaseModel


class AdminStatsResponse(BaseModel):
    """
    Aggregate stats for the admin dashboard.
    All counts are integers — never null.
    """
    # Users
    users_total:   int
    users_active:  int

    # Plans
    plans_total:   int
    plans_active:  int

    # Bots
    bots_total:    int
    bots_running:  int
    bots_stopped:  int
    bots_error:    int

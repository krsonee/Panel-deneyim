"""FSM states for the guided media-generation conversation.

Flow:
    main menu
      -> choosing_category      (Casino / Spor Bahis)
      -> choosing_theme         (theme within the chosen category)
      -> entering_subject       (game/team name, free text)
      -> entering_custom_details (optional extra art direction, free text)
      -> choosing_output_type   (Görsel / Video / Sticker)
      -> confirming             (review the built prompt, confirm or cancel)
      -> generating             (busy state while a provider call is in flight)
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class GenerationStates(StatesGroup):
    choosing_category = State()
    choosing_theme = State()
    entering_subject = State()
    entering_custom_details = State()
    choosing_output_type = State()
    confirming = State()
    generating = State()

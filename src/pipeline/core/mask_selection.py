import math
from typing import TypedDict


class BoxSelection(TypedDict):
    bbox: list[int | float]


SelectionChoice = int | None | BoxSelection


def validate_selection(
    choice: SelectionChoice, candidate_count: int, image_width: int, image_height: int
) -> SelectionChoice:
    """Validate a selection in original-image pixel coordinates."""
    if choice is None:
        return None
    if isinstance(choice, int) and not isinstance(choice, bool):
        if 0 <= choice < candidate_count:
            return choice
        raise ValueError("choice index is outside the candidate range")
    if not isinstance(choice, dict) or set(choice) != {"bbox"}:
        raise ValueError('choice must be an integer, null, or {"bbox": [x1, y1, x2, y2]}')
    bbox = choice["bbox"]
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError("bbox must be an array of exactly four finite numbers")
    for value in bbox:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or (isinstance(value, float) and not math.isfinite(value))
        ):
            raise ValueError("bbox coordinates must be finite numbers, not booleans")
    x1, y1, x2, y2 = bbox
    if not (0 <= x1 < x2 <= image_width and 0 <= y1 < y2 <= image_height):
        raise ValueError("bbox must be ordered xyxy coordinates within the source image")
    if x2 - x1 < 1 or y2 - y1 < 1:
        raise ValueError("bbox width and height must each be at least one pixel")
    return {"bbox": list(bbox)}


def resolve_selection(
    choice: SelectionChoice,
    candidates: list[list[float]],
    image_width: int,
    image_height: int,
) -> list[int | float] | None:
    choice = validate_selection(choice, len(candidates), image_width, image_height)
    if choice is None:
        return None
    if isinstance(choice, int):
        return candidates[choice]
    return choice["bbox"]

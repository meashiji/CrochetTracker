"""Static stitch reference data (US notation).

Pure data module with no dependencies: the panel route and its tests both
import this constant, keeping the rendered reference and the contract tests
on a single source of truth.
"""

from typing import TypedDict


class Stitch(TypedDict):
    """One entry of the stitch reference panel."""

    name: str
    symbol: str
    description: str
    category: str


STITCHES: tuple[Stitch, ...] = (
    {
        "name": "chain",
        "symbol": "ch",
        "description": "Foundation stitch that creates a chain. The starting point for most projects.",
        "category": "foundational",
    },
    {
        "name": "single crochet",
        "symbol": "sc",
        "description": "Short, dense stitch. The most commonly used stitch in crochet.",
        "category": "foundational",
    },
    {
        "name": "double crochet",
        "symbol": "dc",
        "description": "Taller stitch that creates a more open, lacy fabric.",
        "category": "foundational",
    },
    {
        "name": "half double crochet",
        "symbol": "hdc",
        "description": "Stitch taller than single but shorter than double. Good for quick growth.",
        "category": "foundational",
    },
    {
        "name": "treble crochet",
        "symbol": "tr",
        "description": "The tallest of the basic stitches. Creates a very open fabric.",
        "category": "foundational",
    },
    {
        "name": "magic ring",
        "symbol": "magic circle",
        "description": "Start working in a circle without a central hole. Ideal for amigurumi and circular projects.",
        "category": "special",
    },
    {
        "name": "increase",
        "symbol": "inc",
        "description": 'Work 2 stitches into the same stitch to add a stitch. Often written as "2 sc in next st".',
        "category": "increase",
    },
    {
        "name": "decrease",
        "symbol": "dec",
        "description": 'Work 2 stitches together to remove a stitch. Commonly written as "sc2tog" (single crochet 2 together).',
        "category": "decrease",
    },
)

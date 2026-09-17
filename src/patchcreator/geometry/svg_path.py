"""Adapt SVG path-data strings to PatchCreator measurable path samplers.

FontTools already contains a standards-aware SVG path parser, so PatchCreator
reuses it instead of maintaining a second SVG tokenizer.  The parsed pen
operations are converted into the small LinePath/CubicBezierPath/CompoundPath
geometry model used by placement and text outlining.
"""

from __future__ import annotations

import math

from fontTools.pens.recordingPen import RecordingPen
from fontTools.svgLib.path.parser import parse_path

from .paths import CompoundPath, CubicBezierPath, LinePath, MeasurablePathSampler
from .transform import Point

_EPSILON = 1e-10


class SvgPathSamplingError(ValueError):
    """SVG path data cannot be represented as one measurable PatchCreator path."""


def _point(value: object) -> Point:
    try:
        x, y = value  # type: ignore[misc]
        return float(x), float(y)
    except (TypeError, ValueError) as exc:
        raise SvgPathSamplingError(f"invalid point emitted by SVG path parser: {value!r}") from exc


def _same(first: Point, second: Point) -> bool:
    return math.hypot(first[0] - second[0], first[1] - second[1]) <= _EPSILON


def _quadratic_to_cubic(start: Point, control: Point, end: Point) -> CubicBezierPath:
    return CubicBezierPath(
        start=start,
        control1=(
            start[0] + (2.0 / 3.0) * (control[0] - start[0]),
            start[1] + (2.0 / 3.0) * (control[1] - start[1]),
        ),
        control2=(
            end[0] + (2.0 / 3.0) * (control[0] - end[0]),
            end[1] + (2.0 / 3.0) * (control[1] - end[1]),
        ),
        end=end,
    )


def _qcurve_segments(start: Point, values: tuple[object, ...]) -> tuple[CubicBezierPath, ...]:
    if not values or values[-1] is None:
        raise SvgPathSamplingError("SVG quadratic path did not provide an explicit end point")
    points = tuple(_point(value) for value in values)
    if len(points) < 2:
        raise SvgPathSamplingError("quadratic SVG path requires a control point and end point")

    controls = points[:-1]
    explicit_end = points[-1]
    current = start
    result: list[CubicBezierPath] = []
    for index, control in enumerate(controls):
        if index == len(controls) - 1:
            end = explicit_end
        else:
            next_control = controls[index + 1]
            end = (
                (control[0] + next_control[0]) / 2.0,
                (control[1] + next_control[1]) / 2.0,
            )
        result.append(_quadratic_to_cubic(current, control, end))
        current = end
    return tuple(result)


def svg_path_sampler(path_data: str) -> MeasurablePathSampler:
    """Parse one SVG path-data string into a measurable path sampler.

    The current adapter intentionally accepts exactly one connected subpath.
    Relative commands and elliptical arcs are handled by FontTools; arcs are
    emitted as cubic curves.  Quadratic curves are converted exactly to cubic
    Beziers.  A closing ``Z`` contributes the closing line when necessary.
    """

    if not path_data or not path_data.strip():
        raise SvgPathSamplingError("SVG path data is empty")

    pen = RecordingPen()
    try:
        parse_path(path_data, pen)
    except Exception as exc:
        raise SvgPathSamplingError(f"cannot parse SVG path data: {exc}") from exc

    segments: list[MeasurablePathSampler] = []
    current: Point | None = None
    subpath_start: Point | None = None
    move_count = 0

    for operator, args in pen.value:
        if operator == "moveTo":
            move_count += 1
            if move_count > 1:
                raise SvgPathSamplingError(
                    "SVG path contains multiple disconnected subpaths; only one is supported"
                )
            if len(args) != 1:
                raise SvgPathSamplingError("unexpected moveTo operation in SVG path")
            current = _point(args[0])
            subpath_start = current
            continue

        if current is None or subpath_start is None:
            raise SvgPathSamplingError("SVG path drawing command appeared before moveTo")

        if operator == "lineTo":
            if len(args) != 1:
                raise SvgPathSamplingError("unexpected lineTo operation in SVG path")
            end = _point(args[0])
            if not _same(current, end):
                segments.append(LinePath(current, end))
            current = end
            continue

        if operator == "curveTo":
            if len(args) == 0 or len(args) % 3:
                raise SvgPathSamplingError("unsupported cubic pen operation in SVG path")
            for offset in range(0, len(args), 3):
                control1 = _point(args[offset])
                control2 = _point(args[offset + 1])
                end = _point(args[offset + 2])
                segments.append(CubicBezierPath(current, control1, control2, end))
                current = end
            continue

        if operator == "qCurveTo":
            produced = _qcurve_segments(current, tuple(args))
            segments.extend(produced)
            current = produced[-1].end
            continue

        if operator == "closePath":
            if not _same(current, subpath_start):
                segments.append(LinePath(current, subpath_start))
            current = subpath_start
            continue

        if operator == "endPath":
            continue

        raise SvgPathSamplingError(f"unsupported SVG pen operation {operator!r}")

    if move_count == 0:
        raise SvgPathSamplingError("SVG path does not contain a moveTo command")
    if not segments:
        raise SvgPathSamplingError("SVG path has no measurable segments")
    if len(segments) == 1:
        return segments[0]
    return CompoundPath(tuple(segments))

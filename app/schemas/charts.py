from typing import Dict, Any, List

_VEGA_SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"


class ChartSpecBuilder:
    """Programmatic generator of declarative Vega-Lite and ECharts JSON specifications.

    `build_scatter_regression_chart` stays available for callers that already
    hold point rows. Regression results do not include those rows, so the
    HTTP and MCP regression responses do not attach it.
    """

    @staticmethod
    def build_waterfall_chart(
        data: List[Dict[str, Any]],
        category_field: str,
        value_field: str,
        title: str = "Driver Attribution Waterfall"
    ) -> Dict[str, Any]:
        return {
            "$schema": _VEGA_SCHEMA,
            "title": title,
            "data": {"values": data},
            "transform": [
                {
                    "window": [{"op": "sum", "field": value_field, "as": "end"}],
                    "frame": [None, 0],
                },
                {"calculate": f"datum.end - datum.{value_field}", "as": "start"},
            ],
            "mark": {"type": "bar", "tooltip": True},
            "encoding": {
                "x": {"field": category_field, "type": "ordinal", "sort": None},
                "y": {"field": "start", "type": "quantitative"},
                "y2": {"field": "end"},
                "color": {
                    "condition": {"test": f"datum.{value_field} > 0", "value": "#2ca02c"},
                    "value": "#d62728",
                },
            },
        }

    @staticmethod
    def build_scatter_regression_chart(
        data: List[Dict[str, Any]],
        x_field: str,
        y_field: str,
        title: str = "Scatter Regression Fit"
    ) -> Dict[str, Any]:
        return {
            "$schema": _VEGA_SCHEMA,
            "title": title,
            "layer": [
                {
                    "data": {"values": data},
                    "mark": "point",
                    "encoding": {
                        "x": {"field": x_field, "type": "quantitative"},
                        "y": {"field": y_field, "type": "quantitative"},
                    },
                },
                {
                    "data": {"values": data},
                    "mark": {"type": "line", "color": "firebrick"},
                    "transform": [{"regression": y_field, "on": x_field}],
                    "encoding": {
                        "x": {"field": x_field, "type": "quantitative"},
                        "y": {"field": y_field, "type": "quantitative"},
                    },
                },
            ],
        }

    @staticmethod
    def build_time_series_forecast_chart(
        historical: List[Dict[str, Any]],
        forecasts: List[Dict[str, Any]],
        time_field: str,
        value_field: str
    ) -> Dict[str, Any]:
        # Forecast payloads are already normalized to time/value and step/predicted_value.
        # time_field and value_field name the source columns for callers; the spec uses the normalized fields.
        _ = (time_field, value_field)
        combined_data = [
            {"time": h["time"], "val": h["value"], "type": "Historical"}
            for h in historical
        ] + [
            {
                "time": f"T+{f['step']}",
                "val": f["predicted_value"],
                "type": "Forecast",
                "lower": f["ci_95_lower"],
                "upper": f["ci_95_upper"],
            }
            for f in forecasts
        ]
        return {
            "$schema": _VEGA_SCHEMA,
            "title": "Time Series Forecast with 95% Confidence Interval",
            "data": {"values": combined_data},
            "layer": [
                {
                    "transform": [{"filter": "datum.type == 'Forecast'"}],
                    "mark": {"type": "errorband"},
                    "encoding": {
                        "x": {"field": "time", "type": "ordinal"},
                        "y": {"field": "lower", "type": "quantitative"},
                        "y2": {"field": "upper"},
                    },
                },
                {
                    "mark": "line",
                    "encoding": {
                        "x": {"field": "time", "type": "ordinal", "sort": None},
                        "y": {"field": "val", "type": "quantitative"},
                        "color": {"field": "type", "type": "nominal"},
                    },
                },
            ],
        }

    @staticmethod
    def build_funnel_chart(
        steps: List[Dict[str, Any]],
        title: str = "Conversion Funnel",
    ) -> Dict[str, Any]:
        values = [
            {"step": step.get("step_name"), "users": step.get("user_count", 0)}
            for step in steps
        ]
        return {
            "$schema": _VEGA_SCHEMA,
            "title": title,
            "data": {"values": values},
            "mark": {"type": "bar", "tooltip": True},
            "encoding": {
                "x": {"field": "step", "type": "ordinal", "sort": None},
                "y": {"field": "users", "type": "quantitative"},
            },
        }

    @staticmethod
    def build_sankey_chart(
        nodes: List[Dict[str, Any]],
        links: List[Dict[str, Any]],
        title: str = "User Flow",
    ) -> Dict[str, Any]:
        return {
            "title": {"text": title},
            "tooltip": {"trigger": "item"},
            "series": [
                {
                    "type": "sankey",
                    "data": nodes,
                    "links": links,
                    "emphasis": {"focus": "adjacency"},
                }
            ],
        }

    @staticmethod
    def build_retention_heatmap(
        matrix: List[Dict[str, Any]],
        title: str = "Cohort Retention",
    ) -> Dict[str, Any]:
        values = []
        for row in matrix:
            cohort = row.get("cohort_date")
            for key, cell in row.items():
                if not str(key).startswith("day_") or not isinstance(cell, dict):
                    continue
                day_token = str(key).split("_", 1)[1]
                if not day_token.isdigit():
                    continue
                values.append({
                    "cohort": str(cohort),
                    "day": int(day_token),
                    "rate": cell.get("rate", 0),
                })
        return {
            "$schema": _VEGA_SCHEMA,
            "title": title,
            "data": {"values": values},
            "mark": "rect",
            "encoding": {
                "x": {"field": "day", "type": "ordinal"},
                "y": {"field": "cohort", "type": "ordinal"},
                "color": {"field": "rate", "type": "quantitative"},
            },
        }

from typing import Dict, Any, List, Optional

class ChartSpecBuilder:
    """Programmatic generator of declarative Vega-Lite and ECharts JSON specifications."""

    @staticmethod
    def build_waterfall_chart(
        data: List[Dict[str, Any]],
        category_field: str,
        value_field: str,
        title: str = "Driver Attribution Waterfall"
    ) -> Dict[str, Any]:
        return {
            "": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title,
            "data": {"values": data},
            "mark": {"type": "bar", "tooltip": True},
            "encoding": {
                "x": {"field": category_field, "type": "nominal", "sort": None},
                "y": {"field": value_field, "type": "quantitative"},
                "color": {
                    "condition": {"test": f"datum.{value_field} > 0", "value": "#2ca02c"},
                    "value": "#d62728"
                }
            }
        }

    @staticmethod
    def build_scatter_regression_chart(
        data: List[Dict[str, Any]],
        x_field: str,
        y_field: str,
        title: str = "Scatter Regression Fit"
    ) -> Dict[str, Any]:
        return {
            "": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title,
            "layer": [
                {
                    "data": {"values": data},
                    "mark": "point",
                    "encoding": {
                        "x": {"field": x_field, "type": "quantitative"},
                        "y": {"field": y_field, "type": "quantitative"}
                    }
                },
                {
                    "data": {"values": data},
                    "mark": {"type": "line", "color": "firebrick"},
                    "transform": [{"regression": y_field, "on": x_field}],
                    "encoding": {
                        "x": {"field": x_field, "type": "quantitative"},
                        "y": {"field": y_field, "type": "quantitative"}
                    }
                }
            ]
        }

    @staticmethod
    def build_time_series_forecast_chart(
        historical: List[Dict[str, Any]],
        forecasts: List[Dict[str, Any]],
        time_field: str,
        value_field: str
    ) -> Dict[str, Any]:
        combined_data = [
            {"time": h["time"], "val": h["value"], "type": "Historical"}
            for h in historical
        ] + [
            {"time": f"T+{f['step']}", "val": f["predicted_value"], "type": "Forecast", "lower": f["ci_95_lower"], "upper": f["ci_95_upper"]}
            for f in forecasts
        ]
        return {
            "": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": "Time Series Forecast with 95% Confidence Interval",
            "data": {"values": combined_data},
            "mark": "line",
            "encoding": {
                "x": {"field": "time", "type": "ordinal"},
                "y": {"field": "val", "type": "quantitative"},
                "color": {"field": "type", "type": "nominal"}
            }
        }

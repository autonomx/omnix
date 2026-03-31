def adapt_pipeline_result(raw):
    return {
        "success": raw.get("success", True),
        "events": raw.get("events", [])
    }
"""Presentation evidence shared by the single agent and existing review UI."""

def tool_evidence(name: str, result: dict[str, object]) -> dict[str, object]:
    evidence: dict[str, object] = {"tool": name}
    if name in {'compare_latest_ride', 'analyze_sprint_intervals', 'get_activity_stream', 'find_fit_fields', 'get_fit_activity_data', 'analyze_activity_climbs','analyze_activity_sections'}:
        evidence.update(result)
    elif name == 'get_cycling_workout_variants':
        evidence.update(result)
    elif name in {'query_app_data','get_app_data_catalog','get_garmin_strength_catalog'}:
        evidence.update(result)
    elif name == "propose_training_event":
        evidence["training_event"] = result["training_event"] if result.get("training_event") else None
    elif name == "propose_training_setup":
        evidence["training_setup"] = result
    elif name == "propose_training_adjustment":
        evidence["training_adjustment"] = result
    elif name == "preview_training_plan":
        evidence["coaching"] = result
    elif name == "create_plots":
        evidence["plots"] = result["plots"]
    elif name == "get_projected_training_readiness":
        evidence.update(period={"start":result["date"],"end":result["date"]},limitations=result["limitations"]+result["assumptions"])
    elif name == "get_training_readiness":
        evidence.update(period={"start": result['date'], "end": result['date']}, limitations=[result['caution'],result['reconstruction']])
    elif name == "get_health_summary":
        evidence.update(
            {
                "period": result["period"],
                "freshness": result["freshness"],
                "record_count": result["evidence"]["record_count"],
                "missing_metric_types": result["missing_metric_types"],
                "metrics": result['metrics'],
            }
        )
    elif name == "list_activities":
        evidence.update(
            {
                "period": result["period"],
                "freshness": result["freshness"],
                "total_matches": result["total_matches"],
                "returned_count": result["returned_count"],
                "truncated": result["truncated"],
                "records": [
                    {
                        "id": item["id"],
                        "activity_type": item["activity_type"],
                        "local_date": item["local_date"],
                        "url": item["evidence_url"],
                    }
                    for item in result["activities"]
                ],
            }
        )
    elif name == "compare_periods":
        evidence.update(
            {
                "period_a": result["period_a"]["period"],
                "period_b": result["period_b"]["period"],
                "period_a_activity_ids": result["period_a"]["activities"][
                    "activity_ids"
                ],
                "period_b_activity_ids": result["period_b"]["activities"][
                    "activity_ids"
                ],
                "limitations": result["limitations"],
            }
        )
    elif name == "find_similar_rides":
        reference = result["reference_ride"]
        evidence.update(
            {
                "period": result["candidate_period"],
                "freshness": result["freshness"],
                "candidate_pool_count": result["candidate_pool_count"],
                "evaluated_count": result["evaluated_count"],
                "total_matches": result["total_matches"],
                "returned_count": result["returned_count"],
                "truncated": result["truncated"],
                "criteria": result["criteria"],
                "unavailable_criteria": result["unavailable_criteria"],
                "reference_record": {
                    "id": reference["id"],
                    "name": reference["name"],
                    "activity_type": reference["activity_type"],
                    "local_date": reference["local_date"],
                    "url": reference["evidence_url"],
                },
                "records": [
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "activity_type": item["activity_type"],
                        "local_date": item["local_date"],
                        "similarity_score": item["similarity_score"],
                        "url": item["evidence_url"],
                    }
                    for item in result["rides"]
                ],
                "limitations": result["limitations"],
            }
        )
    elif name == "find_same_course_rides":
        reference = result["reference_ride"]
        evidence.update(
            {
                "period": result["candidate_period"],
                "freshness": result["freshness"],
                "candidate_pool_count": result["candidate_pool_count"],
                "evaluated_count": result["gps_candidates_evaluated"],
                "total_matches": result["total_matches"],
                "returned_count": result["returned_count"],
                "truncated": result["truncated"],
                "criteria": result["criteria"],
                "unavailable_criteria": result["unavailable_criteria"],
                "reference_record": {
                    "id": reference["id"],
                    "name": reference["name"],
                    "activity_type": reference["activity_type"],
                    "local_date": reference["local_date"],
                    "url": reference["evidence_url"],
                },
                "records": [
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "activity_type": item["activity_type"],
                        "local_date": item["local_date"],
                        "route_overlap_percent": item["route_match"][
                            "route_overlap_percent"
                        ],
                        "direction": item["route_match"]["direction"],
                        "endpoint_distance_meters": item["route_match"][
                            "endpoint_distance_meters"
                        ],
                        "url": item["evidence_url"],
                    }
                    for item in result["rides"]
                ],
                "course_progress": result["course_progress"],
                "privacy": result["privacy"],
                "limitations": result["limitations"],
            }
        )
    elif name == "assess_ride":
        reference = result["reference_ride"]
        evidence.update({"period": result["period"], "freshness": result["freshness"],
                         "limitations": result["limitations"],
                         "reference_record": {"id": reference["id"], "name": reference["name"],
                             "activity_type": reference["activity_type"], "local_date": reference["local_date"], "url": reference["evidence_url"]}})
    elif name in {"list_maintenance", "export_maintenance"}:
        evidence["maintenance"] = result
    elif name == "propose_settings_change":
        evidence["proposal"] = result["proposal"]
    elif name == "running_volume_trend":
        evidence.update({"period": result["period"], "limitations": result["limitations"],
            "records": [{"id": identifier, "activity_type": "running", "local_date": week["period"]["start"],
                         "url": f"/api/activities/{identifier}"} for week in result["weeks"] for identifier in week["activity_ids"]]})
    return evidence

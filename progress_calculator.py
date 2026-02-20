def calculate_project_progress(tasks: list) -> float:
    """
    Calculates project progress based on completed task weights.
    Only tasks with status == "Completed" contribute.
    """

    if not tasks:
        return 0.0

    total_weight = sum(task.get("weight", 0) for task in tasks)

    if total_weight == 0:
        return 0.0

    completed_weight = sum(
        task.get("weight", 0)
        for task in tasks
        if task.get("status") == "Completed"
    )

    progress = (completed_weight / total_weight) * 100
    return round(progress, 2)
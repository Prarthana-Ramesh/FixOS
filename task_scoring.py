tasks = {
    "high_cpu": {
        "expected_actions": ["check_process", "reduce_load"]
    },
    "normal": {
        "expected_actions": []
    }
}

def agent_from_kernel(kernel):

    if kernel.cpu == "BUSY":
        return {
            "problem": "high_cpu",
            "actions": ["check_process"]
        }
    else:
        return {
            "problem": "normal",
            "actions": []
        }

def check_problem(agent_output):
    if agent_output["problem"] in tasks:
        return 1
    return 0

def check_actions(agent_output):
    problem = agent_output["problem"]
    expected = tasks[problem]["expected_actions"]

    if len(expected) == 0:
        return 1

    correct = 0
    for act in agent_output["actions"]:
        if act in expected:
            correct += 1

    return correct / len(expected)

def get_score(agent_output):
    p = check_problem(agent_output)
    a = check_actions(agent_output)

    return (p + a) / 2
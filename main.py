import tkinter as tk
from collections import deque
import time
from task_scoring import agent_from_kernel, get_score

# -------- PROCESS --------
class Process:
    def __init__(self, pid, burst, priority, memory, disk):
        self.pid = pid
        self.remaining = burst
        self.priority = priority
        self.memory = memory
        self.disk = disk
        self.state = "READY"

# -------- KERNEL --------
class Kernel:
    def __init__(self, time_quantum=2):
        self.queues = {}
        self.pid_counter = 1
        self.time_quantum = time_quantum
        self.gantt = []
        self.cpu = "IDLE"
        self.mem_used = 0
        self.disk_used = 0
        self.processes = []   # FIX: missing list

    def create_process(self, burst, priority, memory, disk):
        p = Process(self.pid_counter, burst, priority, memory, disk)

        if self.mem_used + memory > 100 or self.disk_used + disk > 100:
            return "Not enough resources"

        self.mem_used += memory
        self.disk_used += disk

        if priority not in self.queues:
            self.queues[priority] = deque()

        self.queues[priority].append(p)
        self.processes.append(p)

        self.pid_counter += 1
        return f"Process {p.pid} created"

    def scheduler(self):
        log = ""

        while any(self.queues.values()):
            active = sorted([p for p in self.queues if self.queues[p]])
            if not active:
                break

            highest = active[0]
            queue = self.queues[highest]

            current = queue.popleft()
            current.state = "RUNNING"
            self.cpu = "BUSY"

            exec_time = min(self.time_quantum, current.remaining)  # FIX
            time.sleep(0.2)
            current.remaining -= exec_time

            self.gantt.append("P" + str(current.pid))

            if current.remaining > 0:
                current.state = "WAITING"
                queue.append(current)
                log += f"Process {current.pid} paused\n"
            else:
                current.state = "TERMINATED"
                self.mem_used -= current.memory
                self.disk_used -= current.disk
                log += f"Process {current.pid} completed\n"

            self.cpu = "IDLE"

        return log


# -------- GUI --------
kernel = Kernel()

def create_process():
    try:
        result = kernel.create_process(
            int(burst_entry.get()),
            int(priority_entry.get()),
            int(memory_entry.get()),
            int(disk_entry.get())
        )
        output.insert(tk.END, result + "\n")
    except:
        output.insert(tk.END, "Invalid input\n")


def run_scheduler():
    output.insert(tk.END, "\nRunning Scheduler...\n")

    log = kernel.scheduler()
    output.insert(tk.END, log)

    # -------- CONNECT TO TASK SYSTEM --------
    agent_output = agent_from_kernel(kernel)
    score = get_score(agent_output)

    output.insert(tk.END, "\nAgent Output:\n")
    output.insert(tk.END, str(agent_output) + "\n")
    output.insert(tk.END, f"Score: {score}\n")


def show_status():
    output.insert(tk.END, "\nSYSTEM STATUS\n")
    output.insert(tk.END, f"CPU: {kernel.cpu}\n")
    output.insert(tk.END, f"Memory: {kernel.mem_used}/100\n")
    output.insert(tk.END, f"Disk: {kernel.disk_used}/100\n")

    for p in kernel.processes:
        output.insert(tk.END, f"P{p.pid} - {p.state} - Remaining: {p.remaining}\n")


def show_gantt():
    output.insert(tk.END, "\nGANTT CHART\n")
    for g in kernel.gantt:
        output.insert(tk.END, "| " + g + " ")
    output.insert(tk.END, "|\n")


# -------- WINDOW --------
root = tk.Tk()
root.title("Mini OS Simulator")
root.geometry("600x500")

tk.Label(root, text="Burst").pack()
burst_entry = tk.Entry(root)
burst_entry.pack()

tk.Label(root, text="Priority").pack()
priority_entry = tk.Entry(root)
priority_entry.pack()

tk.Label(root, text="Memory").pack()
memory_entry = tk.Entry(root)
memory_entry.pack()

tk.Label(root, text="Disk").pack()
disk_entry = tk.Entry(root)
disk_entry.pack()

tk.Button(root, text="Create Process", command=create_process).pack(pady=5)
tk.Button(root, text="Run Scheduler", command=run_scheduler).pack(pady=5)
tk.Button(root, text="Show Status", command=show_status).pack(pady=5)
tk.Button(root, text="Show Gantt", command=show_gantt).pack(pady=5)

output = tk.Text(root, height=15)
output.pack()

root.mainloop()
import subprocess, os
p=subprocess.run(["ps","-C","postgres","-o","args="],capture_output=True,text=True)
assert "/var/tmp/saas-full-" not in p.stdout
p=subprocess.run(["ps","-C","python,node,cp","-o","pid=,args="],capture_output=True,text=True)
assert not [line for line in p.stdout.splitlines() if int(line.split()[0]) != os.getpid()]
print("All session test Python/Node/copy processes and private Postgres clusters stopped.")

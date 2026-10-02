data=open("out/login_diag.log","rb").read().decode("gbk",errors="replace")
lines=[l for l in data.splitlines() if l.strip()]
for l in lines[-14:]:
    print(l[:220])

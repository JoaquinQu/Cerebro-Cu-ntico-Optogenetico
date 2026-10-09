"""Genera las figuras de teoria_cerebro_cuantico.tex con el mismo codigo del proyecto.

    python docs/teoria_tex/generar_figuras.py
"""
import os, sys, json, math
from pathlib import Path
import numpy as np
AQUI=Path(__file__).resolve().parent
RAIZ=str(AQUI.parent.parent/"qollab"); os.chdir(RAIZ); sys.path.insert(0,RAIZ)
from cerebro_q import fisica, circuitos, analisis, datos
from cerebro_q.microcircuitos import MICROCIRCUITOS
from scipy.linalg import expm
import matplotlib; matplotlib.use("pdf")
import matplotlib.pyplot as plt
OUT=str(AQUI/"figuras"); os.makedirs(OUT,exist_ok=True)
C=["#2a78d6","#eb6834","#1baf7a","#eda100","#e87ba4","#008300","#6250d6","#e34948"]
INK="#0b0b0b"; INK2="#52514e"; GRID="#e4e3df"
plt.rcParams.update({"font.size":9,"axes.edgecolor":INK2,"axes.labelcolor":INK,"xtick.color":INK2,"ytick.color":INK2,
  "axes.grid":True,"grid.color":GRID,"grid.linewidth":0.6,"axes.spines.top":False,"axes.spines.right":False,
  "lines.linewidth":1.8,"legend.frameon":False,"font.family":"serif","mathtext.fontset":"cm"})
info={}
J,nombres,escala=fisica.acoplamientos(); info["lambda_max"]=escala; info["N"]=len(J)
info["aristas"]=int((np.triu(J,1)>0).sum())
eig=fisica.diagonalizacion()
info["Jmin_pos"]=float(J[J>0].min()); info["Jmax"]=float(J.max())
lam=eig[0]; info["lam_min"]=float(lam.min()); info["lam_max"]=float(lam.max())
# --- Fig 1: walk cuántico vs difusión clásica en la red completa
j=fisica.indice("AVM"); ts=np.linspace(0,60,241)
P=fisica.probabilidades_walk(eig,j,ts,math.pi,1.0)
L=np.diag(J.sum(1))-J
lamL,VL=np.linalg.eigh(L)
Pc=np.array([ (VL*np.exp(-lamL*t))@VL[j] for t in ts])
pos=np.array([d["y"] for d in datos.neuronas()])
def spread(PP):
    q=PP/PP.sum(1,keepdims=True); m=q@pos; return np.sqrt(np.maximum(q@pos**2-m**2,0))
def part(PP):
    q=PP/PP.sum(1,keepdims=True); return 1/np.sum(q**2,1)
fig,ax=plt.subplots(1,2,figsize=(6.4,2.5))
ax[0].plot(ts,part(P),color=C[0],label="cuántico")
ax[0].plot(ts,part(Pc),color=C[1],label="clásico (difusión)")
ax[0].set_xlabel(r"$t\ [1/\gamma]$"); ax[0].set_ylabel("participación efectiva")
ax[1].plot(ts,spread(P),color=C[0],label="cuántico"); ax[1].plot(ts,spread(Pc),color=C[1],label="clásico (difusión)")
ax[1].set_xlabel(r"$t\ [1/\gamma]$"); ax[1].set_ylabel(r"dispersión anteroposterior [$\mu$m]")
ax[0].legend(loc="lower right")
fig.tight_layout(); fig.savefig(f"{OUT}/fig_walk_vs_clasico.pdf"); plt.close(fig)
info["part_q_60"]=float(part(P)[-1]); info["part_c_60"]=float(part(Pc)[-1])
# llegada a ALML y AVDL
for nm in ["ALML","AVDL"]:
    k=fisica.indice(nm); pk=P[:,k]; info[f"tmax_{nm}"]=float(ts[np.argmax(pk[:60])])

# --- Fig 1c: participacion y probabilidad de retorno (memoria del walk)
ts3=np.linspace(0,300,1201)
P3=fisica.probabilidades_walk(eig,j,ts3,math.pi,1.0)
Pc3=np.array([(VL*np.exp(-lamL*t))@VL[j] for t in ts3])
lamS,VS=eig; o=np.argsort(lamS); lamS=lamS[o]; VS=VS[:,o]
Pbar=np.zeros(len(J)); g=[0]
for m in range(1,len(lamS)+1):
    if m<len(lamS) and abs(lamS[m]-lamS[g[-1]])<1e-9: g.append(m); continue
    Pbar+=(VS[:,g]@VS[j,g])**2
    if m<len(lamS): g=[m]
info["retorno_promedio"]=float(Pbar[j]); info["retorno_x_n"]=float(Pbar[j]*len(J))
fig,ax=plt.subplots(1,2,figsize=(6.4,2.5))
ax[0].plot(ts3,part(P3),color=C[0],label="cuántico"); ax[0].plot(ts3,part(Pc3),color=C[1],label="clásico")
ax[0].set_xlabel(r"$t\ [1/\gamma]$"); ax[0].set_ylabel("participación efectiva"); ax[0].legend(loc="lower right")
nret=len(J)
ax[1].plot(ts3,nret*P3[:,j],color=C[0],lw=1.0,label="cuántico")
ax[1].plot(ts3,nret*Pc3[:,j],color=C[1],label="clásico")
ax[1].axhline(nret*Pbar[j],color=C[6],ls="--",lw=1.2,label="promedio temporal")
ax[1].set_yscale("log"); ax[1].set_ylim(0.3,400)
ax[1].set_xlabel(r"$t\ [1/\gamma]$"); ax[1].set_ylabel(r"$n\,P_{jj}(t)$  (retorno a AVM)"); ax[1].legend(loc="upper right",fontsize=7.5)
fig.tight_layout(); fig.savefig(f"{OUT}/fig_retorno.pdf"); plt.close(fig)
# --- Fig 1b: cadena 1D (balístico vs difusivo)
n=201; A=np.zeros((n,n))
for i in range(n-1): A[i,i+1]=A[i+1,i]=1
lamA,VA=np.linalg.eigh(A); LA=np.diag(A.sum(1))-A; lamLA,VLA=np.linalg.eigh(LA)
c=n//2; xs=np.arange(n)-c; tt=np.linspace(0,60,121)
sq=[];sc=[]
for t in tt:
    a=(VA*np.exp(-1j*lamA*t))@VA[c]; p=np.abs(a)**2; sq.append(np.sqrt(p@xs**2))
    p=(VLA*np.exp(-lamLA*t))@VLA[c]; sc.append(np.sqrt(p@xs**2))
tq=40.0; aq=np.abs((VA*np.exp(-1j*lamA*tq))@VA[c])**2; pc=(VLA*np.exp(-lamLA*tq))@VLA[c]
fig,ax=plt.subplots(1,2,figsize=(6.4,2.5))
ax[0].plot(xs,aq,color=C[0],lw=1.2,label="cuántico"); ax[0].plot(xs,pc,color=C[1],label="clásico")
ax[0].set_xlabel("sitio $x$"); ax[0].set_ylabel(r"$P(x,\,t=40)$"); ax[0].legend(loc="upper left")
ax[1].plot(tt,sq,color=C[0],label=r"cuántico $\propto t$"); ax[1].plot(tt,sc,color=C[1],label=r"clásico $\propto\sqrt{t}$")
ax[1].set_xlabel(r"$t\ [1/\gamma]$"); ax[1].set_ylabel(r"$\sigma(t)$ [sitios]"); ax[1].legend(loc="upper left")
fig.tight_layout(); fig.savefig(f"{OUT}/fig_cadena.pdf"); plt.close(fig)
info["sigma_q_40"]=float(sq[80]); info["sigma_c_40"]=float(sc[80])
# --- Fig 2: toque-6 exacto + puntos de Trotter
m=MICROCIRCUITOS["toque-6"]; nm6=m["neuronas"]; Js=fisica.sub_acoplamientos(nm6)
info["toque6_aristas"]=int((np.triu(Js,1)>0).sum())
ts2=np.linspace(0,45,181); Ps=fisica.probabilidades_walk(np.linalg.eigh(Js),0,ts2,math.pi,1.0)
tp=np.array([5,10,15,20,25,30,35,40,45.])
fig,ax=plt.subplots(figsize=(6.4,2.7))
for k,n in enumerate(nm6):
    ax.plot(ts2,Ps[:,k],color=C[k],label=n)
    vals=[]
    for t in tp:
        ops=circuitos.operaciones(6,[0],math.pi,circuitos.saltos_trotter(Js,t,2,1.0,2))
        vals.append(analisis.marginales(circuitos.probabilidades_ideales(ops,6),6)[k])
    ax.plot(tp,vals,"o",ms=4.5,color=C[k],mec="white",mew=1.0)
ax.set_xlabel(r"$t\ [1/\gamma]$"); ax.set_ylabel(r"$P_k(t)$"); ax.set_ylim(0,1.02)
ax.legend(ncol=6,loc="upper center",bbox_to_anchor=(0.5,1.17),handlelength=1.4,columnspacing=1.0)
fig.tight_layout(); fig.savefig(f"{OUT}/fig_toque6.pdf"); plt.close(fig)
# --- Fig 3: error de Trotter vs r y presupuesto
t=30.0; ex=fisica.distribucion_exacta(Js,[0],math.pi,t,1.0)
rs=np.arange(1,17); e1=[];e2=[];nzz=[]
for r in rs:
    for o,arr in ((1,e1),(2,e2)):
        ops=circuitos.operaciones(6,[0],math.pi,circuitos.saltos_trotter(Js,t,int(r),1.0,o))
        arr.append(analisis.tvd(ex,circuitos.probabilidades_ideales(ops,6)))
        if o==2: nzz.append(circuitos.recursos(ops))
# error de operador
H=np.zeros((64,64),complex)
X=np.array([[0,1],[1,0]]);Y=np.array([[0,-1j],[1j,0]]);I=np.eye(2)
def op2(P,a,b):
    mats=[I]*6; mats[a]=P; mats[b]=P; M=mats[5]
    for q in range(4,-1,-1): M=np.kron(M,mats[q])
    return M
E=circuitos.aristas(Js)
for a,b,w in E: H+=w*(op2(X,a,b)+op2(Y,a,b))/2
U=expm(-1j*H*t)
def Utrot(r,o):
    ops=circuitos.operaciones(6,[],0,circuitos.saltos_trotter(Js,t,int(r),1.0,o))
    M=np.eye(64,dtype=complex)
    for op in ops:
        col=np.zeros(64,complex)
        pass
    # construir por columnas con el simulador
    cols=[]
    for i in range(64):
        psi=np.zeros(64,complex); psi[i]=1
        for op in ops: psi=circuitos._aplicar(psi,6,op,circuitos._matriz(op))
        cols.append(psi)
    return np.array(cols).T
o1=[np.linalg.norm(U-Utrot(r,1),2) for r in rs]; o2=[np.linalg.norm(U-Utrot(r,2),2) for r in rs]
fig,ax=plt.subplots(1,2,figsize=(6.4,2.6))
ax[0].loglog(rs,o1,"-o",ms=3.5,color=C[0],label="1er orden")
ax[0].loglog(rs,o2,"-o",ms=3.5,color=C[1],label="2º orden (Strang)")
rr=np.array([4,16.]); ax[0].loglog(rr,o1[3]*(4/rr),":",color=INK2,lw=1); ax[0].loglog(rr,o2[3]*(4/rr)**2,":",color=INK2,lw=1)
ax[0].text(7,o1[3]*4/7*1.45,r"$\propto 1/r$",color=INK2); ax[0].text(10.5,0.04,r"$\propto 1/r^2$",color=INK2)
ax[0].set_xlabel("pasos de Trotter $r$"); ax[0].set_ylabel(r"$\|e^{-iHt}-U(t/r)^r\|_2$"); ax[0].legend(loc="lower left")
F=np.array([x["fidelidad_estimada"] for x in nzz]); e2=np.array(e2)
rk=rs[:8]
ax[1].plot(rk,e2[:8],"-o",ms=3.5,color=C[0],label="error de Trotter (TVD)")
ax[1].plot(rk,1-F[:8],"-o",ms=3.5,color=C[1],label=r"error de hardware $1-F_{hw}$")
ax[1].plot(rk,e2[:8]+1-F[:8],"-o",ms=3.5,color=C[6],label="total")
rstar=int(rk[np.argmin(e2[:8]+1-F[:8])]); ax[1].axvline(rstar,color=INK2,ls=":",lw=1)
ax[1].text(rstar+0.15,0.72,f"$r^*={rstar}$",color=INK)
ax[1].set_xlabel("pasos de Trotter $r$"); ax[1].set_ylim(0,1); ax[1].legend(loc="upper left",bbox_to_anchor=(0.3,1.02),fontsize=7.5)
fig.tight_layout(); fig.savefig(f"{OUT}/fig_trotter.pdf"); plt.close(fig)
info["tvd2"]={int(r):float(v) for r,v in zip(rs[:6],e2[:6])}; info["tvd1"]={int(r):float(v) for r,v in zip(rs[:6],e1[:6])}
info["F"]={int(r):float(v) for r,v in zip(rs[:6],F[:6])}; info["nzz"]={int(r):x["compuertas_2q"] for r,x in zip(rs[:6],nzz[:6])}
info["rstar"]=rstar; info["op1"]=[float(x) for x in o1[:4]]; info["op2"]=[float(x) for x in o2[:4]]
# cota de conmutadores 1er orden
def P2(a,b,w): return w*(op2(X,a,b)+op2(Y,a,b))/2
hs=[P2(a,b,w) for a,b,w in E]; s=0
for i in range(len(hs)):
    for k in range(i+1,len(hs)): s+=np.linalg.norm(hs[i]@hs[k]-hs[k]@hs[i],2)
info["cota1_r2"]=float(t**2/(2*2)*s)
# --- Fig 4: post-selección con ruido
ops=circuitos.operaciones(6,[0],math.pi,circuitos.saltos_trotter(Js,t,2,1.0,2))
ruido=circuitos.probabilidades_con_ruido(ops,6,trayectorias=400)
comp=analisis.comparar(ex,ruido,6,1); info["post"]={k:(v if isinstance(v,float) else None) for k,v in comp.items()}
ideal=circuitos.probabilidades_ideales(ops,6)
series=[("teoría exacta",analisis.marginales(ex,6),C[0]),("circuito ideal ($r=2$)",analisis.marginales(ideal,6),C[1]),
        ("con ruido, bruto",comp["marginales_bruto"],C[2]),("con ruido, post-seleccionado",comp["marginales_postseleccion"],C[6])]
fig,ax=plt.subplots(figsize=(6.4,2.5)); w=0.2; x=np.arange(6)
for i,(lab,v,c) in enumerate(series): ax.bar(x+(i-1.5)*w,v,w*0.9,color=c,label=lab)
ax.set_xticks(x); ax.set_xticklabels(nm6); ax.set_ylabel(r"$P_k(t=30)$"); ax.grid(axis="x",visible=False)
ax.legend(ncol=2,fontsize=7.5,loc="upper left")
fig.tight_layout(); fig.savefig(f"{OUT}/fig_postseleccion.pdf"); plt.close(fig)
# peso por sector de Hamming en ruido
hw=analisis.peso_hamming(np.arange(64)); info["sectores_ruido"]=[float(ruido[hw==h].sum()) for h in range(4)]
print(json.dumps(info,indent=1,ensure_ascii=False))

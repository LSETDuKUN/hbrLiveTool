"""Probability masses on a shared absolute grid; no random sampling."""
import math
import cmath


def fft(a,inverse=False):
    n=len(a);j=0
    for i in range(1,n):
        bit=n>>1
        while j&bit:j^=bit;bit>>=1
        j^=bit
        if i<j:a[i],a[j]=a[j],a[i]
    size=2
    while size<=n:
        root=cmath.exp((2j if inverse else -2j)*math.pi/size)
        for start in range(0,n,size):
            w=1
            for k in range(size//2):
                u=a[start+k];v=w*a[start+k+size//2]
                a[start+k]=u+v;a[start+k+size//2]=u-v;w*=root
        size*=2
    if inverse:
        for i in range(n):a[i]/=n


def convolve(a,b):
    n=1
    while n<len(a)+len(b)-1:n*=2
    x=list(a)+[0.]*(n-len(a));y=list(b)+[0.]*(n-len(b))
    fft(x);fft(y)
    for i in range(n):x[i]*=y[i]
    fft(x,True)
    return [max(0,v.real) for v in x[:len(a)+len(b)-1]]


def advance(mass,amount,step):
    """Convolve with one U(.9 amount, 1.1 amount) by prefix integration."""
    if amount==0:return mass[:]
    lo,hi=.9*amount,1.1*amount
    size=len(mass)+math.ceil(hi/step)+1
    if len(mass)==1:
        return [mass[0]*max(0,min((i+.5)*step,hi)-max((i-.5)*step,lo))/(hi-lo) for i in range(size)]
    prefix=[0.]
    for p in mass:prefix.append(prefix[-1]+p)
    def cdf(x):
        pos=x/step+.5
        if pos<=0:return 0.
        if pos>=len(mass):return prefix[-1]
        i=int(pos)
        return prefix[i]+(pos-i)*mass[i]
    result=[max(0,(cdf(i*step-lo)-cdf(i*step-hi))*step/(hi-lo)) for i in range(size)]
    total=sum(result)
    return [p*prefix[-1]/total for p in result] if total else result


def split(mass,threshold,step):
    """Keep subthreshold and first-crossing mass, including raw overshoot."""
    if threshold is None:return mass[:],[0.]*len(mass)
    below=[p*min(1,max(0,threshold/step-i+.5)) for i,p in enumerate(mass)]
    return below,[max(0,p-q) for p,q in zip(mass,below)]


def add(target,source):
    target.extend([0.] * max(0,len(source)-len(target)))
    for i,p in enumerate(source):target[i]+=p


def stopped(amounts,hp,step):
    alive=[1.];result=[]
    for amount in amounts:
        alive=advance(alive,amount,step)
        alive,dead=split(alive,hp,step)
        add(result,dead)
        if sum(alive)<1e-14:break
    add(result,alive)
    return result

"""Causal display filters; counts in/counts out. No ECG validity inference."""
import math

class Biquad:
    def __init__(self, kind, fs, f, q=2**-0.5):
        w=2*math.pi*f/fs;c=math.cos(w);a=math.sin(w)/(2*q)
        if kind=='high':b=[(1+c)/2,-(1+c),(1+c)/2]
        elif kind=='low':b=[(1-c)/2,1-c,(1-c)/2]
        elif kind=='notch':b=[1,-2*c,1]
        else:raise ValueError(kind)
        self.b=[x/(1+a) for x in b];self.a1=-2*c/(1+a);self.a2=(1-a)/(1+a)
        self.z1=self.z2=0.0
    def prime(self,x):
        y=sum(self.b)/(1+self.a1+self.a2)*x
        self.z1=y-self.b[0]*x;self.z2=self.b[2]*x-self.a2*y
        return y
    def step(self,x):
        y=self.b[0]*x+self.z1
        self.z1=self.b[1]*x-self.a1*y+self.z2
        self.z2=self.b[2]*x-self.a2*y
        return y

class SignalFilter:
    def __init__(self,fs=239.0):
        if not 100<=fs<=1200:raise ValueError('Fs must be 100..1200 Hz')
        self.fs=fs
        self.stages=[Biquad('high',fs,.5),Biquad('notch',fs,50,20),Biquad('low',fs,40)]
        self.ready=False;self.age=0
    def reset(self):self.ready=False;self.age=0
    def push(self,x,gap=False):
        clipped=abs(x)>=32700
        if gap or clipped:self.reset()
        if not self.ready:
            v=x
            for stage in self.stages:v=stage.prime(v)
            self.ready=True
        y=float(x)
        for stage in self.stages:y=stage.step(y)
        self.age+=1
        valid=(not clipped and self.age>=int(2*self.fs))
        if clipped:self.reset()
        return y,valid,clipped

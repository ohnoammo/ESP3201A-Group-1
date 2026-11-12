import matplotlib.pyplot as plt
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11})
bg='#fbfaf8'; txt='#444444'; grid='#e3e3e3'
before_c='#b8c4d6'; after_c='#1bb07b'
data={'Pool A':[('Fixed 512/77',1,0.856,0.923),('Structural cap 256',0.5,0.666,0.924),('Size-matched 110',1,0.605,0.763)],
      'Pool H':[('Fixed 512/77',0.5,0.820,0.890),('Structural cap 256',0.25,0.559,0.858),('Size-matched 111',0.5,0.525,0.698)]}
fig,axes=plt.subplots(1,2,figsize=(11.5,4.6),sharey=True,facecolor=bg)
w=0.36
for ax,(pool,rows) in zip(axes,data.items()):
    ax.set_facecolor(bg)
    for i,(name,a,b0,b1) in enumerate(rows):
        r0=ax.bar(i-w/2-0.01,b0,w,color=before_c,label='No links (α = 0)' if i==0 else None)
        r1=ax.bar(i+w/2+0.01,b1,w,color=after_c,label='Links at selected α' if i==0 else None)
        ax.text(i-w/2-0.01,b0+0.015,f'{b0:.3f}',ha='center',va='bottom',color=txt,fontsize=10)
        ax.text(i+w/2+0.01,b1+0.015,f'{b1:.3f}',ha='center',va='bottom',color=txt,fontsize=10)
    ax.set_xticks(range(3)); ax.set_xticklabels([f'{n}\nα = {a:g}' for n,a,_,_ in rows],color=txt)
    ax.set_title(pool,color=txt,fontsize=12,loc='left')
    ax.set_ylim(0,1.05); ax.yaxis.grid(True,color=grid); ax.set_axisbelow(True)
    for s in ['top','right','left']: ax.spines[s].set_visible(False)
    ax.spines['bottom'].set_color('#888888'); ax.tick_params(colors='#888888',length=0)
axes[0].set_ylabel('Budget line recall (test, n = 181)',color=txt)
fig.suptitle('Exp 1, dense retrieval, 2,560-token budget: links raise budget line recall most for structural chunks',x=0.06,ha='left',color=txt,fontsize=12.5)
h,l=axes[0].get_legend_handles_labels()
fig.legend(h,l,loc='lower left',bbox_to_anchor=(0.06,-0.02),ncol=2,frameon=False,labelcolor=txt)
fig.tight_layout(rect=(0,0.06,1,0.95))
fig.savefig('fig_exp1_links.png',dpi=200,facecolor=bg)

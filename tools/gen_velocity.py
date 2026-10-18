#!/usr/bin/env python3
# VELOCITY only — full car always visible: blurred bg (same photo) fills the frame,
# sharp uncropped car floats on the Velocity stage. Sizes keyed to u=min(W,H)/100.
import json, os, html

IMG = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"velocity_imgs.json")))
CARS = {
 "sienna":   dict(year="20XX", make="Toyota",        model="Sienna",         trim="LE · 8-Passenger",     body="Minivan",   drive="FWD",     km="165,000", price="18,000", eng="3.5L V6", tag="Family Hauler"),
 "mercedes": dict(year="20XX", make="Mercedes-Benz", model="E 350",          trim="4MATIC · Premium",     body="Sedan",     drive="AWD",     km="126,000", price="17,900", eng="3.5L V6", tag="Luxury AWD"),
 "santafe":  dict(year="20XX", make="Hyundai",        model="Santa Fe Sport", trim="2.4L · Heated Seats",  body="SUV",       drive="FWD/AWD", km="107,000", price="14,000", eng="2.4L I4", tag="Certified"),
 "elantra":  dict(year="20XX", make="Hyundai",        model="Elantra GT",     trim="GLS · Hatchback",      body="Hatchback", drive="FWD",     km="96,000", price="12,000", eng="2.0L I4", tag="Fuel Saver"),
 "buick":    dict(year="20XX", make="Buick",          model="LaCrosse",       trim="Premium · Leather",    body="Sedan",     drive="FWD",     km="83,000", price="11,500", eng="3.6L V6", tag="Showroom Ready"),
}
ORDER=["sienna","mercedes","santafe","elantra","buick"]
PHONE="1 613 447 4520"
EMAIL="omarranwar58@gmail.com"
FORMATS={"phone":(1080,2340),"social":(1080,1350),"landscape":(1920,1080)}
F_COND="Archivo,'Arial Narrow','Helvetica Neue',Impact,sans-serif"
F_BODY="Inter,'Helvetica Neue',Arial,sans-serif"
IMPORT=("<style>@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@600;700;800&amp;"
        "family=Inter:wght@400;500;600;700;800&amp;display=swap');</style>")
def e(s): return html.escape(str(s),quote=True)
def tw(s,fs,k=0.56): return len(str(s))*fs*k
def txt(x,y,s,fs,fill,family=F_BODY,weight="400",anchor="start",ls=0,upper=False):
    s=str(s).upper() if upper else str(s)
    st=f'font-family:{family};font-size:{fs:.1f}px;font-weight:{weight};fill:{fill};'
    if ls: st+=f'letter-spacing:{ls:.2f}px;'
    return f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" style="{st}">{e(s)}</text>'

def velocity(W,H,c):
    u=min(W,H)/100; m=6*u; acc="#19e36a"; uid=f'{c["key"]}{W}'
    d=IMG[c["key"]]
    o=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{F_BODY}">{IMPORT}']
    o.append('<defs>'
        f'<clipPath id="fr{uid}"><rect width="{W}" height="{H}"/></clipPath>'
        f'<linearGradient id="vg{uid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#070a0f" stop-opacity=".60"/><stop offset=".30" stop-color="#070a0f" stop-opacity=".12"/>'
        f'<stop offset=".60" stop-color="#070a0f" stop-opacity=".40"/><stop offset="1" stop-color="#070a0f" stop-opacity=".98"/></linearGradient>'
        f'<radialGradient id="vr{uid}" cx="50%" cy="34%" r="62%">'
        f'<stop offset="0" stop-color="#1d2735" stop-opacity="0"/><stop offset="1" stop-color="#070a0f" stop-opacity=".55"/></radialGradient>'
        f'<radialGradient id="vglow{uid}" cx="50%" cy="50%" r="55%">'
        f'<stop offset="0" stop-color="#19e36a" stop-opacity=".16"/><stop offset="1" stop-color="#19e36a" stop-opacity="0"/></radialGradient>'
        f'<filter id="sh{uid}" x="-20%" y="-20%" width="140%" height="140%">'
        f'<feDropShadow dx="0" dy="{1.2*u:.1f}" stdDeviation="{2.2*u:.1f}" flood-color="#000000" flood-opacity="0.55"/></filter>'
        '</defs>')
    o.append(f'<rect width="{W}" height="{H}" fill="#0a0e14"/>')
    # blurred background (cover) + brand veils
    o.append(f'<image x="0" y="0" width="{W}" height="{H}" preserveAspectRatio="xMidYMid slice" clip-path="url(#fr{uid})" href="{d["blur"]}"/>')
    o.append(f'<rect width="{W}" height="{H}" fill="url(#vr{uid})"/>')
    o.append(f'<rect width="{W}" height="{H}" fill="url(#vg{uid})"/>')
    # ── photo zone (safe region above the text block) ──
    portrait = W<=H
    cardTop=12*u; cardBottom=H-46*u
    regionH=cardBottom-cardTop; rad=1.8*u
    shots=d["shots"]
    def photo(x,y,w,h,src,i):
        cid=f"c{uid}{i}"
        o.append(f'<clipPath id="{cid}"><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rad:.1f}"/></clipPath>')
        o.append(f'<image x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" preserveAspectRatio="xMidYMid slice" '
                 f'clip-path="url(#{cid})" filter="url(#sh{uid})" href="{src}"/>')
    # choose how many shots to show: phone stacks 2, landscape 2 side-by-side, social 1
    if portrait and len(shots)>=2:          # vertical stack
        g=2.4*u; boxW=W-2*m
        hs=[boxW/s["ar"] for s in shots[:2]]
        total=sum(hs)+g
        if total>regionH:
            sc=regionH/total; boxW*=sc; hs=[hh*sc for hh in hs]; total=regionH
        x=(W-boxW)/2; y=cardTop+(regionH-total)/2
        o.append(f'<ellipse cx="{W/2:.1f}" cy="{cardTop+regionH/2:.1f}" rx="{boxW*0.6:.1f}" ry="{total*0.55:.1f}" fill="url(#vglow{uid})"/>')
        for i in range(2):
            photo(x,y,boxW,hs[i],shots[i]["sharp"],i); y+=hs[i]+g
    elif (not portrait) and len(shots)>=2:  # side-by-side
        g=2.2*u; h=regionH
        ws=[h*s["ar"] for s in shots[:2]]
        total=sum(ws)+g; maxW=W-2*m
        if total>maxW:
            sc=maxW/total; h*=sc; ws=[ww*sc for ww in ws]; total=maxW
        x=(W-total)/2; y=cardTop+(regionH-h)/2
        o.append(f'<ellipse cx="{W/2:.1f}" cy="{cardTop+regionH/2:.1f}" rx="{total*0.58:.1f}" ry="{h*0.6:.1f}" fill="url(#vglow{uid})"/>')
        for i in range(2):
            photo(x,y,ws[i],h,shots[i]["sharp"],i); x+=ws[i]+g
    else:                                   # single hero
        ar=shots[0]["ar"]; maxW=W-(8*u if portrait else 16*u)
        cw=maxW; ch=cw/ar
        if ch>regionH: ch=regionH; cw=ch*ar
        cx=(W-cw)/2; cy=(cardTop+3.5*u) if portrait else (cardTop+(regionH-ch)/2)
        o.append(f'<ellipse cx="{cx+cw/2:.1f}" cy="{cy+ch/2:.1f}" rx="{cw*0.62:.1f}" ry="{ch*0.6:.1f}" fill="url(#vglow{uid})"/>')
        photo(cx,cy,cw,ch,shots[0]["sharp"],0)
    # ── top band ──
    ly=m+3.4*u
    o.append(f'<rect x="{m:.1f}" y="{ly-2.5*u:.1f}" width="{2.3*u:.1f}" height="{2.3*u:.1f}" fill="{acc}"/>')
    o.append(txt(m+3.2*u,ly-0.5*u,"PRE-OWNED",2.3*u,"#fff",F_COND,"800",upper=True,ls=2))
    o.append(txt(W-m,ly-0.3*u,c["tag"],1.9*u,acc,F_COND,"700",anchor="end",upper=True,ls=1.5))
    o.append(txt(W-m,ly+1.9*u,f'{c["drive"]} · {c["body"]}',1.5*u,"#92a2b2",F_COND,"700",anchor="end",upper=True,ls=1.5))
    # ── bottom text block ──
    priceB=H-8*u; priceT=priceB-11*u
    specsB=priceT-3*u; specsT=specsB-9*u
    trimBase=specsT-3*u
    o.append(txt(m,trimBase,c["trim"],2.5*u,"#c3cedb",F_BODY,"600"))
    o.append(txt(m,trimBase-3.4*u,c["model"],8.4*u,"#fff",F_COND,"800",upper=True,ls=-1))
    o.append(txt(m,trimBase-3.4*u-7.6*u,f'{c["year"]} · {c["make"]}',2.4*u,acc,F_COND,"700",upper=True,ls=3))
    o.append(f'<line x1="{m}" y1="{specsT:.1f}" x2="{W-m}" y2="{specsT:.1f}" stroke="#ffffff33"/>')
    o.append(f'<line x1="{m}" y1="{specsB:.1f}" x2="{W-m}" y2="{specsB:.1f}" stroke="#ffffff33"/>')
    colw=(W-2*m)/3
    for i,(b,s) in enumerate([(c["km"],"KM"),(c["eng"],"Engine"),(c["drive"],"Drivetrain")]):
        cxx=m+colw*(i+0.5)
        if i>0: o.append(f'<line x1="{m+colw*i:.1f}" y1="{specsT+1.2*u:.1f}" x2="{m+colw*i:.1f}" y2="{specsB-1.2*u:.1f}" stroke="#ffffff24"/>')
        o.append(txt(cxx,specsT+4.6*u,b,3.1*u,"#fff",F_COND,"800",anchor="middle"))
        o.append(txt(cxx,specsT+6.6*u,s,1.5*u,"#8ea0b5",F_COND,"700",anchor="middle",upper=True,ls=2))
    ptxt="$"+c["price"]; pfs=5.4*u; pw=tw(ptxt,pfs,0.6)+9*u; px0=W-pw; slant=2.2*u
    o.append(f'<polygon points="{px0+slant:.1f},{priceT:.1f} {W},{priceT:.1f} {W},{priceB:.1f} {px0:.1f},{priceB:.1f}" fill="{acc}"/>')
    o.append(txt(W-3*u,priceT+3.3*u,"PRICED TO SELL",1.5*u,"#04140a",F_COND,"700",anchor="end",upper=True,ls=2))
    o.append(txt(W-3*u,priceB-2.4*u,ptxt,pfs,"#04140a",F_COND,"800",anchor="end"))
    # contact strip: phone, then email, then the tax note
    cy=H-3.4*u; cx=m
    o.append(txt(cx,cy,PHONE,2.2*u,"#fff",F_COND,"700",ls=.5))
    cx+=tw(PHONE,2.2*u,0.56)+2.2*u
    o.append(txt(cx,cy,"·",2.0*u,"#ffffff55",F_BODY,"600")); cx+=1.9*u
    o.append(txt(cx,cy,EMAIL,1.95*u,acc,F_BODY,"600"))
    # tax note pinned to the right margin so it can never collide with the email
    o.append(txt(W-m,cy,"+ tax & lic",1.9*u,"#aeb9c6",F_BODY,"500",anchor="end"))
    o.append("</svg>"); return "".join(o)

def main():
    import shutil
    if os.path.isdir("output/svg"): shutil.rmtree("output/svg")
    os.makedirs("output/svg",exist_ok=True)
    n=0
    for ck in ORDER:
        c=dict(CARS[ck]); c["key"]=ck
        for fmt,(W,H) in FORMATS.items():
            open(f"output/svg/{ck}_{fmt}.svg","w").write(velocity(W,H,c)); n+=1
    print("generated",n,"velocity svg files")
if __name__=="__main__": main()

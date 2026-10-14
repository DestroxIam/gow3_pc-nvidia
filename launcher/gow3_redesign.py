"""Native Tk presentation layer. Settings and launch behavior remain in the existing launcher."""
from pathlib import Path
import sys
import tkinter as tk

PAGE = '#030b10'
PANEL = '#071218'
CARD = '#101c24'
LINE = '#263b47'
TEXT = '#eee7da'
MUTED = '#a1adb5'
RED = '#ef271f'
HOVER = '#ff4035'
ASSETS = ((Path(sys.executable).resolve().parent / 'launcher') if getattr(sys, 'frozen', False)
          else Path(__file__).resolve().parent) / 'redesign-assets'

def rounded(canvas, x0, y0, x1, y1, radius, **options):
    r=min(radius,(x1-x0)/2,(y1-y0)/2)
    points=(x0+r,y0,x1-r,y0,x1,y0,x1,y0+r,x1,y1-r,x1,y1,x1-r,y1,
            x0+r,y1,x0,y1,x0,y1-r,x0,y0+r,x0,y0)
    return canvas.create_polygon(points,smooth=True,splinesteps=20,**options)

class NavItem(tk.Canvas):
    def __init__(self,parent,owner,name,title,image):
        self.owner,self.name,self.title,self.image=owner,name,title,image
        self.active=self.hover=False
        super().__init__(parent,bg=PAGE,highlightthickness=0,bd=0,height=owner.px(42),takefocus=True,cursor='hand2')
        self.bind('<Configure>',lambda e:self.draw())
        self.bind('<Enter>',lambda e:self.set_hover(True))
        self.bind('<Leave>',lambda e:self.set_hover(False))
        self.bind('<Button-1>',lambda e:owner.show(name))
        self.bind('<Return>',lambda e:owner.show(name))
        self.bind('<space>',lambda e:owner.show(name))
        self.bind('<FocusIn>',lambda e:self.set_hover(True))
        self.bind('<FocusOut>',lambda e:self.set_hover(False))
    def set_hover(self,value):self.hover=value;self.draw()
    def set_active(self,value):self.active=value;self.draw()
    def draw(self):
        self.delete('all');w=max(10,self.winfo_width());h=self.winfo_height();px=self.owner.px
        if self.active or self.hover:
            rounded(self,px(10),px(2),w-px(10),h-px(2),px(7),
                    fill='#2b1114' if self.active else '#101d26',outline='#642021' if self.active else '#263b47')
        if self.active:self.create_line(px(12),px(8),px(12),h-px(8),fill=HOVER,width=px(3))
        self.create_image(px(31),h/2,image=self.image)
        self.create_text(px(52),h/2,text=self.title,anchor='w',fill=TEXT,
                         font=('Segoe UI',11,'bold' if self.active else 'normal'))

class PlayButton(tk.Canvas):
    def __init__(self,parent,owner,text,command,image):
        self.owner,self.label,self.command,self.image=owner,text,command,image
        self.hover=False;self.disabled=False
        super().__init__(parent,width=owner.px(174),height=owner.px(44),bg=PAGE,bd=0,highlightthickness=0,takefocus=True,cursor='hand2')
        self.bind('<Configure>',lambda e:self.draw())
        self.bind('<Enter>',lambda e:self.set_hover(True))
        self.bind('<Leave>',lambda e:self.set_hover(False))
        self.bind('<Button-1>',lambda e:self.invoke())
        self.bind('<Return>',lambda e:self.invoke())
        self.bind('<space>',lambda e:self.invoke())
    def set_hover(self,value):self.hover=value;self.draw()
    def invoke(self):
        if not self.disabled:self.command()
    def configure(self,cnf=None,**kwargs):
        if cnf is not None:return super().configure(cnf,**kwargs)
        if 'text' in kwargs:self.label=kwargs.pop('text')
        if 'state' in kwargs:self.disabled=kwargs.pop('state')=='disabled'
        answer=super().configure(**kwargs) if kwargs else None
        if hasattr(self,'label'):self.draw()
        return answer
    config=configure
    def draw(self):
        self.delete('all');w=max(self.winfo_width(),self.owner.px(174));h=max(self.winfo_height(),self.owner.px(44));px=self.owner.px
        rounded(self,0,0,w-1,h-1,px(6),fill='#372124' if self.disabled else HOVER if self.hover else RED,outline='#702022' if self.disabled else HOVER)
        if not self.disabled:self.create_image(px(27),h/2,image=self.image)
        self.create_text(w/2+px(7),h/2,text=self.label,fill=MUTED if self.disabled else '#fff7ed',font=('Segoe UI',12,'bold'))

class RedSlider(tk.Canvas):
    def __init__(self,parent,owner,variable,minimum=0,maximum=100,step=1):
        self.owner,self.variable,self.minimum,self.maximum,self.step=owner,variable,float(minimum),float(maximum),step
        self.disabled=False
        super().__init__(parent,width=owner.px(220),height=owner.px(26),bg=PANEL,bd=0,highlightthickness=0,takefocus=True,cursor='hand2')
        self.bind('<Configure>',lambda e:self.draw())
        self.bind('<Button-1>',self.move);self.bind('<B1-Motion>',self.move)
        self.bind('<Left>',lambda e:self.adjust(-step));self.bind('<Right>',lambda e:self.adjust(step))
        self.bind('<Home>',lambda e:self.assign(self.minimum));self.bind('<End>',lambda e:self.assign(self.maximum))
        variable.trace_add('write',lambda *a:self.draw())
    def assign(self,value):
        if self.disabled:return
        value=max(self.minimum,min(self.maximum,value))
        self.variable.set(round(value,2) if self.step<1 else round(value))
    def adjust(self,delta):
        try:self.assign(float(self.variable.get())+delta)
        except (ValueError,tk.TclError):pass
    def move(self,event):
        self.focus_set();pad=self.owner.px(10);width=max(1,self.winfo_width()-2*pad)
        value=self.minimum+(event.x-pad)/width*(self.maximum-self.minimum)
        self.assign(round(value/self.step)*self.step)
    def configure(self,cnf=None,**kwargs):
        if cnf is not None:return super().configure(cnf,**kwargs)
        if 'state' in kwargs:self.disabled=kwargs.pop('state')=='disabled'
        answer=super().configure(**kwargs) if kwargs else None
        if hasattr(self,'variable'):self.draw()
        return answer
    config=configure
    def draw(self):
        if not self.winfo_exists():return
        self.delete('all');px=self.owner.px;w=max(self.winfo_width(),px(220));h=max(self.winfo_height(),px(26))
        try:value=float(self.variable.get())
        except (ValueError,tk.TclError):value=self.minimum
        ratio=max(0,min(1,(value-self.minimum)/max(.001,self.maximum-self.minimum)));pad=px(10);x=pad+ratio*(w-2*pad)
        self.create_line(pad,h/2,w-pad,h/2,fill='#273741',width=px(6),capstyle='round')
        if x>pad:self.create_line(pad,h/2,x,h/2,fill='#65747d' if self.disabled else RED,width=px(6),capstyle='round')
        radius=px(6)
        self.create_oval(x-radius,h/2-radius,x+radius,h/2+radius,fill='#89959d' if self.disabled else '#fff7ed',
                         outline='#67747d' if self.disabled else HOVER,width=px(2))

def apply(base,namespace):
    """Return a presentation subclass without replacing any of the 11 page builders."""
    namespace.update(BG=PAGE,PANEL=PANEL,CARD=CARD,LINE=LINE,TEXT=TEXT,MUTED=MUTED,ACCENT=RED,ACCENT_HI=HOVER)
    tr=namespace['_']
    class RedesignedLauncher(base):
        def __init__(self,*args,**kwargs):
            self._icons={};self._art={};self._headers={};self._inners=[]
            super().__init__(*args,**kwargs)
            # Fit the existing desktop while keeping the sidebar and footer available.
            self.root.geometry(f'{self.px(1240)}x{self.px(840)}')
            self.root.minsize(self.px(1060),self.px(700))
            self.root.after_idle(self.finish_panels)
            self.root.after_idle(self.report_design_metrics)
            self.root.after(300,self.style_window_chrome)
            self.root.bind('<Map>',lambda event:self.root.after(200,self.style_window_chrome)
                           if event.widget is self.root else None,add='+')

        def style_window_chrome(self):
            import ctypes,os
            if os.name!='nt':return
            try:
                from ctypes import wintypes
                ancestor=ctypes.windll.user32.GetAncestor
                ancestor.argtypes=(wintypes.HWND,wintypes.UINT)
                ancestor.restype=wintypes.HWND
                hwnd=ancestor(self.root.winfo_id(),2)
                dwm=ctypes.windll.dwmapi
                self._chrome={'hwnd':int(hwnd),'attributes':{}}
                def set_attribute(code,value):
                    number=ctypes.c_int(value)
                    result=dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd),code,ctypes.byref(number),ctypes.sizeof(number))
                    self._chrome['attributes'][str(code)]=result
                set_attribute(20,1);set_attribute(33,2)
                for code,color in ((34,LINE),(35,PAGE),(36,TEXT)):
                    red,green,blue=(int(color[i:i+2],16) for i in (1,3,5))
                    set_attribute(code,red|(green<<8)|(blue<<16))
                self.report_design_metrics()
            except (OSError,ValueError,AttributeError,tk.TclError):pass

        def ui_icon(self,name,color='white',size=22):
            key=(name,color,size)
            if key not in self._icons:
                photo=tk.PhotoImage(file=str(ASSETS/'icons'/f'{name}-{color}.png'))
                factor=max(1,round(photo.width()/self.px(size)))
                self._icons[key]=photo.subsample(factor)
            return self._icons[key]

        def art(self,name,width):
            key=(name,max(1,round(width/16)))
            if key not in self._art:
                photo=tk.PhotoImage(file=str(ASSETS/f'{name}.png'))
                # Native Tk resampling: no extra runtime dependency in the frozen application.
                denominator=6
                numerator=max(1,round(width*denominator/photo.width()))
                self._art[key]=photo.zoom(numerator, numerator).subsample(denominator,denominator)
                if len(self._art)>10:
                    for old in list(self._art)[:-6]:self._art.pop(old,None)
            return self._art[key]

        def check_images(self):
            dpi=min((100,125,150,200),key=lambda value:abs(value-self.dpi*100))
            self.check_off=tk.PhotoImage(file=str(ASSETS/f'switch-{dpi}-0.png'))
            self.check_on=tk.PhotoImage(file=str(ASSETS/f'switch-{dpi}-1.png'))

        def style(self):
            super().style();s=self.ttk.Style(self.root)
            s.configure('.',font=('Segoe UI',11),background=PANEL,foreground=TEXT,fieldbackground=CARD)
            s.configure('TLabel',font=('Segoe UI',11),background=PANEL,foreground=TEXT)
            s.configure('Muted.TLabel',font=('Segoe UI',10),foreground=MUTED,background=PANEL)
            s.configure('Restart.TLabel',font=('Segoe UI',9,'bold'),foreground=HOVER)
            s.configure('Section.TLabel',font=('Georgia',14,'bold'),foreground=TEXT)
            s.configure('TCombobox',padding=(9,7),arrowcolor=HOVER,foreground=TEXT,bordercolor=LINE)
            s.map('TCombobox',fieldbackground=[('disabled','#0b171e'),('readonly',CARD)],
                  foreground=[('disabled','#65747e'),('readonly',TEXT)],arrowcolor=[('disabled','#65747e'),('readonly',HOVER)])
            s.configure('TEntry',padding=(9,7),fieldbackground=CARD,foreground=TEXT)
            s.configure('TSpinbox',padding=(9,7),fieldbackground=CARD,foreground=TEXT,arrowcolor=HOVER)
            s.configure('TButton',padding=(13,9),font=('Segoe UI',10),background=CARD,bordercolor=LINE)
            s.map('TButton',background=[('active','#1d303c'),('disabled',PANEL)],foreground=[('disabled','#67747d')])
            s.configure('TCheckbutton',background=PANEL,padding=(1,4))
            s.map('TCheckbutton',background=[('active',PANEL)],foreground=[('disabled','#67747d')])
            s.configure('Vertical.TScrollbar',background='#172b37',troughcolor=PAGE,arrowcolor=MUTED,bordercolor=PAGE)
            s.map('Vertical.TScrollbar',background=[('disabled',CARD),('active','#264452')],troughcolor=[('disabled',PAGE)])
            s.configure('Horizontal.TScrollbar',background='#172b37',troughcolor=PAGE,arrowcolor=MUTED,bordercolor=PAGE)
            s.map('Horizontal.TScrollbar',background=[('disabled',CARD),('active','#264452')],troughcolor=[('disabled',PAGE)])
            s.configure('Horizontal.TProgressbar',background=RED,troughcolor=CARD)

        def title_cell(self,parent,title,restart=False):
            cell=self.ttk.Frame(parent)
            self.ttk.Label(cell,text=title,wraplength=self.px(380),justify='left').pack(side='left')
            if restart:self.ttk.Label(cell,text=tr('restart'),style='Restart.TLabel').pack(side='left',padx=(9,0))
            return cell

        def game_changed(self):
            super().game_changed()
            self.side_title.configure(text='R E M A S T E R E D',font=('Georgia',8))

        def nvidia_slider(self,parent,key,title,maximum=100,hint=None):
            holder=self.ttk.Frame(parent);var=self.var(key,'app')
            slider=RedSlider(holder,self,var,maximum=maximum);slider.pack(side='left')
            number=self.ttk.Label(holder,width=5);number.pack(side='left',padx=(self.px(10),0))
            def show(*args):
                try:number.configure(text=f'{round(float(var.get()))}%')
                except (ValueError,tk.TclError):pass
            var.trace_add('write',show);show()
            self.row(parent,title,holder,hint,restart=True)
            return slider

        def build_nvidia(self):
            super().build_nvidia()
            self.nvidia_gpu_label.configure(image=self.ui_icon('cpu'),compound='left',padding=(10,8),font=('Georgia',13,'bold'))
            self.nvidia_image_status.configure(background='#261519',foreground='#ff8174',font=('Segoe UI',10,'bold'),padding=(12,9))
            self.nvidia_image_status.grid_configure(sticky='ew',padx=self.px(30))

        def build_controls(self):
            super().build_controls()
            inner=self.pages['controls']._inner
            for table in inner.winfo_children():
                if not isinstance(table,self.ttk.Frame):continue
                labels=[w for w in table.grid_slaves(row=0) if isinstance(w,self.ttk.Label)]
                if len(labels)==3:
                    table.columnconfigure(1,minsize=self.px(160))
                    for label in labels:
                        label.configure(font=('Georgia',11,'bold'))
                        label.grid_configure(padx=(0,self.px(15)),pady=(0,self.px(8)))

        def build_log(self):
            page=tk.Frame(self.content,bg=PAGE);self.pages['log']=page
            head=tk.Canvas(page,bg=PAGE,height=self.px(133),highlightthickness=0,bd=0);head.pack(fill='x')
            self._headers['log']=(head,tr('Log').upper(),'Diagnóstico da última abertura do jogo.','performance')
            head.bind('<Configure>',lambda e:self.paint_header('log'))
            tools=self.ttk.Frame(page);tools.pack(fill='x',padx=self.px(25),pady=self.px(12))
            self.ttk.Button(tools,text=tr('Copy'),command=self.copy_log).pack(side='right')
            self.ttk.Button(tools,text=tr('Clear'),command=lambda:self.set_log('')).pack(side='right',padx=self.px(8))
            body=tk.Frame(page,bg=PAGE);body.pack(fill='both',expand=True,padx=self.px(25),pady=(0,self.px(22)))
            self.log=tk.Text(body,wrap='none',bg=PANEL,fg='#d7e0e6',insertbackground=TEXT,relief='flat',
                             font=('Consolas',10),padx=self.px(12),pady=self.px(12),state='disabled',highlightthickness=1,highlightbackground=LINE)
            vertical=self.ttk.Scrollbar(body,command=self.log.yview)
            horizontal=self.ttk.Scrollbar(body,orient='horizontal',command=self.log.xview)
            self.log.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
            body.columnconfigure(0,weight=1);body.rowconfigure(0,weight=1)
            self.log.grid(row=0,column=0,sticky='nsew');vertical.grid(row=0,column=1,sticky='ns');horizontal.grid(row=1,column=0,sticky='ew')

        def skin_remaining_sliders(self):
            def walk(widget):
                for child in list(widget.winfo_children()):
                    if isinstance(child,(tk.Scale,self.ttk.Scale)):
                        name=str(child.cget('variable'));var=next((v for v in self.vars.values() if str(v)==name),None)
                        if var is None:continue
                        manager=child.winfo_manager()
                        if manager not in ('pack','grid'):continue
                        info=child.pack_info() if manager=='pack' else child.grid_info()
                        minimum,maximum=float(child.cget('from')),float(child.cget('to'))
                        new=RedSlider(child.master,self,var,minimum,maximum,.05 if maximum-minimum<=2 else 1)
                        child.destroy()
                        if manager=='pack':new.pack(**info)
                        else:new.grid(**info)
                    else:walk(child)
            walk(self.content)

        def report_design_metrics(self):
            import os,json
            from tkinter import font
            target=os.getenv('GOW3_DESIGN_QA_FILE')
            if target:
                report={'pages':list(self.pages),'settings_count':len(self.vars),
                        'body_font':font.Font(root=self.root,font=('Segoe UI',11)).actual(),
                        'heading_font':font.Font(root=self.root,font=('Georgia',25,'bold')).actual(),
                        'window':[self.root.winfo_width(),self.root.winfo_height()],
                        'window_chrome':getattr(self,'_chrome',{}),
                        'art_assets':[str(ASSETS/'performance.png'),str(ASSETS/'nvidia.png')],
                        'controls':[key for key in self.vars]}
                Path(target).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')

        def row(self,parent,title,widget,hint=None,restart=False):
            r=self.next_row(parent)
            holder=self.ttk.Frame(parent)
            holder.grid(row=r,column=0,columnspan=2,sticky='ew',padx=self.px(30),pady=(self.px(9),self.px(9)))
            holder.columnconfigure(0,weight=1)
            self.title_cell(holder,title,restart).grid(row=0,column=0,sticky='w',padx=(0,self.px(20)))
            # Existing widgets were created with `parent`; Tk permits geometry in this descendant.
            widget.grid(in_=holder,row=0,column=1,rowspan=2 if hint else 1,sticky='e',padx=(self.px(10),0))
            widget.tk.call('raise',str(widget))
            if hint:
                note=self.ttk.Label(holder,text=hint,style='Muted.TLabel',justify='left',wraplength=self.px(540))
                note.grid(row=1,column=0,sticky='w',pady=(self.px(5),0),padx=(0,self.px(24)))
                def resize(event):
                    try:note.configure(wraplength=max(self.px(220),event.width-widget.winfo_reqwidth()-self.px(40)))
                    except tk.TclError:pass
                holder.bind('<Configure>',resize)
            return widget

        def note(self,parent,text,top=12):
            self.ttk.Label(parent,text=text,style='Muted.TLabel',wraplength=self.px(830),justify='left').grid(
                row=self.next_row(parent),column=0,columnspan=2,sticky='w',padx=self.px(30),pady=(self.px(top),self.px(6)))

        def section(self,parent,title,top=20):
            r=self.next_row(parent);header=self.ttk.Frame(parent)
            header.grid(row=r,column=0,columnspan=2,sticky='ew',padx=self.px(28),pady=(self.px(top+14),self.px(9)))
            text=title.upper()
            match=(('GERAÇÃO','atom'),('NEURAL','atom'),('QUADROS','gauge'),('SHADER','bolt'),('GPU','cpu'),('DLSS','eye'),
                   ('COMPATIBIL','settings'),('PASTA','folder'),('CONTROLE','device-gamepad-2'))
            name=next((icon for needle,icon in match if needle in text),'adjustments-horizontal')
            self.ttk.Label(header,image=self.ui_icon(name,'red',23)).pack(side='left',padx=(0,self.px(10)))
            self.ttk.Label(header,text=text,font=('Georgia',13,'bold'),foreground=TEXT).pack(side='left')
            tk.Frame(parent,bg=LINE,height=1).grid(row=r+1,column=0,columnspan=2,sticky='ew',padx=self.px(28),pady=(0,self.px(5)))
            if hasattr(parent,'_sections'):parent._sections.append(header)

        def scrolled_page(self,name,title,subtitle=''):
            outer=tk.Frame(self.content,bg=PAGE)
            head=tk.Canvas(outer,bg=PAGE,height=self.px(133),highlightthickness=0,bd=0)
            head.pack(fill='x')
            self._headers[name]=(head,title.upper(),subtitle,'nvidia' if name in ('nvidia','graphics','patches','mods') else 'performance')
            head.bind('<Configure>',lambda e,n=name:self.paint_header(n))
            canvas=tk.Canvas(outer,bg=PAGE,highlightthickness=0,bd=0)
            bar=self.ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
            inner=tk.Frame(canvas,bg=PAGE)
            inner.columnconfigure(0,weight=1);inner.columnconfigure(1,weight=0)
            inner._sections=[]
            inner._back=tk.Canvas(inner,bg=PAGE,highlightthickness=0,bd=0)
            inner._back.place(x=0,y=0,relwidth=1,relheight=1)
            inner.tk.call('lower',str(inner._back))
            item=canvas.create_window(0,0,window=inner,anchor='nw')
            def configure_inner(event):
                canvas.configure(scrollregion=canvas.bbox('all'))
                self.root.after_idle(lambda:self.paint_panels(inner))
            inner.bind('<Configure>',configure_inner)
            canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
            canvas.configure(yscrollcommand=bar.set)
            bar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
            outer.scroll=lambda units:canvas.yview_scroll(units,'units') if inner.winfo_height()>canvas.winfo_height() else None
            outer._inner=inner
            self.pages[name]=outer;self._inners.append(inner)
            return inner

        def paint_header(self,name):
            head,title,subtitle,art=self._headers[name]
            w=max(head.winfo_width(),self.px(600));h=self.px(133);head.delete('all')
            image=self.art(art,w);head._image=image
            head.create_image(w,0,image=image,anchor='ne')
            head.create_text(self.px(30),self.px(40),text=title,anchor='w',fill=TEXT,font=('Georgia',25,'bold'))
            head.create_text(self.px(31),self.px(81),text=subtitle,anchor='nw',width=self.px(545),fill=MUTED,font=('Segoe UI',11))
            head.create_line(0,h-1,w,h-1,fill=LINE)

        def paint_panels(self,inner):
            if not inner.winfo_exists():return
            back=inner._back;back.delete('all');w=inner.winfo_width();h=inner.winfo_height()
            if w<30:return
            headers=inner._sections
            if not headers:
                rounded(back,self.px(14),self.px(4),w-self.px(14),h-self.px(8),self.px(11),fill=PANEL,outline=LINE,width=1)
            for index,header in enumerate(headers):
                y0=header.winfo_y()-self.px(13)
                y1=headers[index+1].winfo_y()-self.px(27) if index+1<len(headers) else h-self.px(8)
                if y1>y0:
                    rounded(back,self.px(14),y0,w-self.px(14),y1,self.px(11),fill=PANEL,outline=LINE,width=1)

        def finish_panels(self):
            for inner in self._inners:
                for widget in inner.grid_slaves():
                    info=widget.grid_info()
                    if str(info.get('in'))==str(inner) and not info.get('padx'):
                        widget.grid_configure(padx=self.px(30))
                tk.Frame(inner,bg=PAGE,height=self.px(22)).grid(row=self.next_row(inner),column=0,columnspan=2)
                self.paint_panels(inner)

        def build(self):
            side=tk.Frame(self.root,bg=PAGE,width=self.px(236));side.pack(side='left',fill='y');side.pack_propagate(False)
            self.side=side
            brand=tk.Frame(side,bg=PAGE);brand.pack(fill='x',padx=self.px(22),pady=(self.px(28),self.px(22)))
            first=tk.Frame(brand,bg=PAGE);first.pack(anchor='w')
            tk.Label(first,text='GOD OF WAR',font=('GodOfWar' if namespace['FONT_LOADED'] else 'Georgia',15),bg=PAGE,fg=TEXT).pack(side='left')
            tk.Label(first,text='III',font=('Georgia',27,'bold'),bg=PAGE,fg=RED).pack(side='left',padx=(3,0))
            self.side_title=tk.Label(brand,text='R E M A S T E R E D',font=('Georgia',8),bg=PAGE,fg=TEXT)
            self.side_title.pack(anchor='w',padx=(4,0))
            self.nav,self.current_page={},None
            items=(('home',tr('Home'),'home'),('display',tr('Display'),'device-desktop'),('nvidia','NVIDIA','eye'),
                   ('graphics',tr('Graphics (experimental)'),'adjustments-horizontal'),('performance',tr('Performance'),'gauge'),
                   ('game',tr('Game'),'swords'),('patches',tr('Patches'),'puzzle'),('mods',tr('Mods'),'atom'),
                   ('controls',tr('Controls'),'device-gamepad-2'),('advanced',tr('Advanced'),'settings'),('log',tr('Log'),'file-text'))
            for name,title,icon in items:
                item=NavItem(side,self,name,title,self.ui_icon(icon));item.pack(fill='x');self.nav[name]=item
            self.side_art=tk.Canvas(side,bg=PAGE,highlightthickness=0,bd=0,height=1)
            self.side_art.pack(fill='both',expand=True,pady=(self.px(12),0))
            def paint_side(event):
                self.side_art.delete('all')
                if event.height>12:
                    image=self.art('nvidia',max(event.width,event.height*3));self.side_art._image=image
                    self.side_art.create_image(event.width,event.height,image=image,anchor='se')
            self.side_art.bind('<Configure>',paint_side)
            self.update_box=None
            self.side_note=tk.Label(side,text=tr('In the game: Insert or R3+L2\nopens the port\'s menu.'),
                                    bg=PAGE,fg=MUTED,font=('Segoe UI',9),wraplength=self.px(195),justify='left')
            self.side_note.pack(anchor='w',padx=self.px(23),pady=(self.px(12),self.px(18)))
            tk.Frame(self.root,bg=LINE,width=1).pack(side='left',fill='y')
            right=tk.Frame(self.root,bg=PAGE);right.pack(side='left',fill='both',expand=True)
            bar=tk.Frame(right,bg=PAGE,height=self.px(72));bar.pack(fill='x',side='bottom');bar.pack_propagate(False)
            tk.Frame(bar,bg=LINE,height=1).pack(fill='x',side='top')
            self.status=tk.Label(bar,text='',bg=PAGE,fg=MUTED,font=('Segoe UI',10),anchor='w',justify='left')
            self.status.pack(side='left',padx=self.px(28))
            self.play_button=PlayButton(bar,self,tr('PLAY'),self.play,self.ui_icon('player-play',size=20))
            self.play_button.pack(side='right',padx=self.px(24),pady=self.px(14))
            self.content=tk.Frame(right,bg=PAGE);self.content.pack(fill='both',expand=True)
            self.pages={}
            self.build_home();self.build_nvidia();self.build_graphics();self.build_display();self.build_performance()
            self.build_game();self.build_patches();self.build_mods();self.build_controls();self.build_advanced();self.build_log()
            self.skin_remaining_sliders()
            self.root.bind_all('<MouseWheel>',self.wheel)
            self.game_changed()

        def show(self,name):
            for page in self.pages.values():page.pack_forget()
            self.pages[name].pack(fill='both',expand=True);self.current_page=name
            for key,item in self.nav.items():item.set_active(key==name)
            if name in ('mods','patches'):self.refresh_lists()
            if name=='patches':self.refresh_game_patches()
            elif name=='graphics':self.refresh_fsr4()
            elif name=='home':self.refresh_status()
            if name in self._headers:self.root.after_idle(lambda:self.paint_header(name))

        def draw_banner(self):
            c=self.banner;w=max(c.winfo_width(),self.px(700));h=int(c['height']);c.delete('all')
            image=self.art('performance',w);c._image=image;c.create_image(w,h/2,image=image,anchor='e')
            c.create_text(self.px(32),h-self.px(105),text='GOD OF WAR III',anchor='w',fill=TEXT,
                          font=('GodOfWar' if namespace['FONT_LOADED'] else 'Georgia',29))
            info=namespace['game_info'](self.meta_dir())
            if info:
                title=namespace['game_profile_of'](self.meta_dir())[0]
                c.create_text(self.px(34),h-self.px(58),text=f'{title} · versão {info[1]}',anchor='w',fill=HOVER,font=('Segoe UI',12,'bold'))
            else:
                c.create_text(self.px(34),h-self.px(58),text=tr('Choose your game folder to play.'),anchor='w',fill=MUTED,font=('Segoe UI',11))
                c.create_window(w-self.px(160),h-self.px(52),window=self.banner_button)

    return RedesignedLauncher

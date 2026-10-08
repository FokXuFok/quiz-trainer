# -*- coding: utf-8 -*-
"""
通用题库刷题练习工具 - 支持导入自定义题库（JSON 格式）
功能：顺序刷题 / 随机刷题 / 模拟考试 / 错题本 / 题库统计
题库文件：tiku.json（与本程序同目录，可在主界面点击【导入题库】替换）
错题记录：wrong.json（自动生成）
做题记录：progress.json（自动生成）
"""

import json
import os
import random
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk

if getattr(sys, "frozen", False):
    BASE = os.path.dirname(sys.executable)
    BUNDLE = getattr(sys, "_MEIPASS", BASE)
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
    BUNDLE = BASE
TIKU_FILE = os.path.join(BASE, "tiku.json")
WRONG_FILE = os.path.join(BASE, "wrong.json")
PROGRESS_FILE = os.path.join(BASE, "progress.json")


def ensure_tiku():
    """打包模式下首次启动：从内置资源释放题库到 exe 同目录（exe 同目录可写）"""
    if os.path.exists(TIKU_FILE) or BUNDLE == BASE:
        return
    src = os.path.join(BUNDLE, "tiku.json")
    if os.path.exists(src):
        try:
            import shutil
            shutil.copy2(src, TIKU_FILE)
        except Exception:
            pass

BG = "#F5F7FA"
FG = "#2B2F36"
BLUE = "#2F6FED"
LIGHT_BLUE = "#E8F0FE"
GREEN = "#1E9E5A"
RED = "#D64545"
FONT = ("Microsoft YaHei", 11)
FONT_BIG = ("Microsoft YaHei", 14, "bold")
FONT_BTN = ("Microsoft YaHei", 11, "bold")


def load_questions():
    with open(TIKU_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["questions"]


def validate_bank(questions):
    """校验导入题库格式，返回 (是否合法, 错误信息或None)"""
    if not isinstance(questions, list) or not questions:
        return False, "题库为空或格式不正确"
    seen = set()
    for i, q in enumerate(questions, 1):
        if not isinstance(q, dict):
            return False, "第 {} 题不是合法的题目对象".format(i)
        if not str(q.get("q", "")).strip():
            return False, "第 {} 题缺少题干 q".format(i)
        if q.get("type") not in ("single", "fill"):
            return False, "第 {} 题 type 必须是 single 或 fill".format(i)
        if q["type"] == "single" and (not q.get("opts") or len(q.get("opts", [])) < 2):
            return False, "第 {} 题单选题缺少选项 opts".format(i)
        if not str(q.get("ans", "")).strip():
            return False, "第 {} 题缺少答案 ans".format(i)
        qid = q.get("id", i)
        if qid in seen:
            return False, "题号 id 重复：{}".format(qid)
        seen.add(qid)
    return True, None


def load_wrong_ids():
    if os.path.exists(WRONG_FILE):
        try:
            with open(WRONG_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_wrong_ids(ids):
    with open(WRONG_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, ensure_ascii=False)


def load_progress():
    """加载做题记录：{题号: 1答对/0答错}"""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                return {int(k): int(v) for k, v in d.items()}
        except Exception:
            pass
    return {}


def save_progress(rec):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False)


def answer_key(ans):
    """填空参考答案的关键表述（取括号说明前的正文，去掉空格）"""
    a = ans.split("（")[0].split("(")[0]
    return a.strip().replace(" ", "").replace("\u3000", "").lower()


def q_type_name(q):
    return {"single": "单选题", "fill": "填空题"}.get(q["type"], "题目")


def center_window(win, w, h):
    """按屏幕尺寸自适应窗口大小并居中，避免内容被屏幕底部截断"""
    sh = win.winfo_screenheight()
    sw = win.winfo_screenwidth()
    w = min(w, sw - 60)
    h = min(h, sh - 120)
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2 - 20)
    win.geometry("{}x{}+{}+{}".format(w, h, x, y))


class StudyWindow(tk.Toplevel):
    """刷题窗口：mode=order/random/wrong"""
    def __init__(self, master, questions, mode="order", title="刷题"):
        super().__init__(master)
        self.questions = questions
        self.mode = mode
        self.idx = 0
        self.results = dict(getattr(master, "progress", {}) or {})   # 含历史做题记录
        self.session_ids = set()          # 本次会话作答过的题号（用于本轮统计）
        self.selected = {}         # id -> 用户选择
        self.var = None            # 当前题 Radio/Entry 变量
        self.wrong_ids = load_wrong_ids()

        self.title(title)
        center_window(self, 1020, 760)
        self.minsize(860, 600)
        self.configure(bg=BG)

        # 顶部信息栏
        top = tk.Frame(self, bg=BLUE)
        top.pack(fill=tk.X)
        self.lb_progress = tk.Label(top, text="", bg=BLUE, fg="white", font=FONT_BIG)
        self.lb_progress.pack(side=tk.LEFT, padx=16, pady=10)
        self.lb_type = tk.Label(top, text="", bg=BLUE, fg="#FFE08A", font=FONT)
        self.lb_type.pack(side=tk.RIGHT, padx=16)

        # 题目区
        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=18, pady=12)

        self.txt_q = tk.Text(body, font=FONT, wrap=tk.WORD, bg="white", relief=tk.FLAT,
                             padx=12, pady=10, spacing1=2, spacing3=4, height=10)
        self.txt_q.pack(fill=tk.BOTH, expand=True)
        self.txt_q.config(state=tk.DISABLED)

        # 选项/答题区
        self.ans_frame = tk.Frame(body, bg="white")
        self.ans_frame.pack(fill=tk.X, pady=(10, 0))

        # 提示/结果标签
        self.lb_result = tk.Label(self.ans_frame, text="", font=FONT_BTN, bg="white")

        # 底部按钮
        bottom = tk.Frame(self, bg=BG)
        bottom.pack(fill=tk.X, padx=18, pady=(0, 14))
        for col in range(6):
            bottom.columnconfigure(col, weight=1)
        self.btn_prev = tk.Button(bottom, text="上一题", font=FONT_BTN, bg="white", fg=FG,
                                  command=self.prev, bd=1, relief=tk.SOLID)
        self.btn_prev.grid(row=0, column=0, sticky="ew", padx=4)
        self.btn_submit = tk.Button(bottom, text="提交作答", font=FONT_BTN, bg=BLUE, fg="white",
                                    command=self.submit, bd=0)
        self.btn_submit.grid(row=0, column=1, sticky="ew", padx=4)
        self.btn_next = tk.Button(bottom, text="下一题", font=FONT_BTN, bg=BLUE, fg="white",
                                  command=self.next, bd=0)
        self.btn_next.grid(row=0, column=2, sticky="ew", padx=4)
        self.btn_wrong = tk.Button(bottom, text="标记/取消错题", font=FONT_BTN, bg="white", fg=FG,
                                   command=self.toggle_wrong, bd=1, relief=tk.SOLID)
        self.btn_wrong.grid(row=0, column=3, sticky="ew", padx=4)
        self.btn_goto = tk.Button(bottom, text="答题卡", font=FONT_BTN, bg="white", fg=FG,
                                  command=self.card, bd=1, relief=tk.SOLID)
        self.btn_goto.grid(row=0, column=4, sticky="ew", padx=4)
        self.btn_close = tk.Button(bottom, text="返回主菜单", font=FONT_BTN, bg="white", fg=FG,
                                   command=self.destroy, bd=1, relief=tk.SOLID)
        self.btn_close.grid(row=0, column=5, sticky="ew", padx=4)

        self.render()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # ---------- 渲染 ----------
    def clear_ans(self):
        for w in self.ans_frame.winfo_children():
            w.destroy()
        self.var = None

    def set_question_text(self, text):
        self.txt_q.config(state=tk.NORMAL)
        self.txt_q.delete("1.0", tk.END)
        self.txt_q.insert("1.0", text)
        self.txt_q.config(state=tk.DISABLED)

    def render(self):
        self.lb_progress.config(text="第 {}/{} 题".format(self.idx + 1, len(self.questions)))
        q = self.questions[self.idx]
        self.lb_type.config(text=q_type_name(q) + " · " + q.get("section", ""))
        self.set_question_text("{}. {}\n".format(q["id"], q["q"]))
        self.clear_ans()

        saved = self.selected.get(q["id"])
        self.btn_submit.config(state=tk.NORMAL)
        if q["type"] == "single":
            self.var = tk.StringVar(value=saved or "")
            row = 0
            letters = "ABCDEFGH"
            for i, opt in enumerate(q.get("opts", [])):
                opt_lb = letters[i] + ") " + opt if not opt[:2].rstrip().endswith(")") else opt
                rb = tk.Radiobutton(self.ans_frame, text="  " + opt_lb, variable=self.var,
                                    value=letters[i], font=FONT, bg="white", anchor="w",
                                    activebackground=LIGHT_BLUE, padx=8, pady=3,
                                    wraplength=940, justify=tk.LEFT,
                                    command=self.on_select)
                rb.grid(row=row, column=0, sticky="ew")
                row += 1
            self.lb_result = tk.Label(self.ans_frame, text="", font=FONT_BTN, bg="white")
            self.lb_result.grid(row=row, column=0, sticky="w", pady=(8, 4), padx=8)
            row += 1
            self.lb_analysis = tk.Label(self.ans_frame, text="", font=FONT, bg="white",
                                        anchor="w", justify=tk.LEFT, wraplength=940)
            self.lb_analysis.grid(row=row, column=0, sticky="ew", padx=8, pady=(2, 8))
        else:
            self.lb_tip = tk.Label(self.ans_frame, text="请在下方输入答案，然后点击【提交作答】核对：",
                                   font=FONT, bg="white", anchor="w")
            self.lb_tip.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 2))
            self.var = tk.StringVar(value=str(saved or ""))
            self.ent = tk.Entry(self.ans_frame, textvariable=self.var, font=FONT, width=60)
            self.ent.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
            self.lb_result = tk.Label(self.ans_frame, text="", font=FONT_BTN, bg="white")
            self.lb_result.grid(row=2, column=0, sticky="w", pady=(8, 4), padx=8)
            row = 3
            self.lb_analysis = tk.Label(self.ans_frame, text="", font=FONT, bg="white",
                                        anchor="w", justify=tk.LEFT, wraplength=940)
            self.lb_analysis.grid(row=row, column=0, sticky="ew", padx=8, pady=(2, 8))

        # 已提交则恢复显示上次结果并锁定
        if q["id"] in self.results:
            self.show_result(q, self.selected.get(q["id"]))

    def show_result(self, q, user):
        ok = self.results.get(q["id"])
        self.btn_submit.config(state=tk.DISABLED)
        single = q["type"] == "single"
        if ok:
            self.lb_result.config(text="✓ 回答正确！", fg=GREEN)
        elif single:
            self.lb_result.config(text="✗ 回答错误，正确答案是 " + q["ans"], fg=RED)
        else:
            self.lb_result.config(text="✗ 回答错误，参考答案是 " + q["ans"], fg=RED)
        ana = str(q.get("analysis", "")).strip()
        if single and not ok:
            txt = "正确答案：" + q["ans"]
            txt += "\n解析：" + ana if ana else "\n（本题暂无解析）"
        elif single:
            txt = "解析：" + ana if ana else "回答正确！（本题暂无解析）"
        elif not ok:
            txt = "参考答案：" + q["ans"]
            txt += "\n解析：" + ana if ana else "\n（本题暂无解析）"
        else:
            txt = "解析：" + ana if ana else "回答正确！（本题暂无解析）"
        self.lb_analysis.config(text=txt)
        # 锁定选项与输入框，防止修改答案
        for w in self.ans_frame.winfo_children():
            if isinstance(w, tk.Radiobutton) or isinstance(w, tk.Entry):
                w.config(state=tk.DISABLED)

    # ---------- 操作 ----------
    def current(self):
        return self.questions[self.idx]

    def get_user_answer(self, q):
        if self.var is None:
            return ""
        if q["type"] == "single":
            return self.var.get()
        return self.var.get().strip()

    def record_answer(self, qid, ok):
        """记录答题结果：更新内存 + 持久化 + 错题本"""
        self.results[qid] = ok
        self.session_ids.add(qid)
        if not ok:
            self.wrong_ids.add(qid)
        else:
            self.wrong_ids.discard(qid)
        save_wrong_ids(self.wrong_ids)
        save_progress(self.results)
        if hasattr(self.master, "progress"):
            self.master.progress.update(self.results)

    def on_select(self):
        """单选题：选中选项后立即判定对错并显示解析"""
        q = self.current()
        if q["type"] != "single":
            return
        user = self.var.get()
        if not user:
            return
        self.selected[q["id"]] = user
        ok = 1 if user == q["ans"] else 0
        self.record_answer(q["id"], ok)
        self.show_result(q, user)

    def submit(self):
        """填空题提交核对（单选题已自动判定）"""
        q = self.current()
        if q["type"] != "fill":
            return
        user = self.get_user_answer(q)
        if not user:
            messagebox.showwarning("提示", "请先作答再提交！", parent=self)
            return
        self.selected[q["id"]] = user
        key = answer_key(q["ans"])
        ok = 1 if key in answer_key(user)[:20] and key else 0
        self.record_answer(q["id"], ok)
        self.show_result(q, user)

    def next(self):
        if self.idx < len(self.questions) - 1:
            self.idx += 1
            self.render()
        else:
            done = sum(1 for qid in self.session_ids if self.results.get(qid) == 1)
            total = len(self.session_ids)
            rate = (done / total * 100) if total else 0
            messagebox.showinfo("完成", "本轮刷题完成！\n已答 {} 题，正确 {} 题，正确率 {:.1f}%".format(total, done, rate), parent=self)

    def prev(self):
        if self.idx > 0:
            self.idx -= 1
            self.render()

    def toggle_wrong(self):
        qid = self.current()["id"]
        if qid in self.wrong_ids:
            self.wrong_ids.discard(qid)
            messagebox.showinfo("错题本", "已从错题本移除本题", parent=self)
        else:
            self.wrong_ids.add(qid)
            messagebox.showinfo("错题本", "已加入错题本", parent=self)
        save_wrong_ids(self.wrong_ids)

    def card(self):
        CardWindow(self, self.questions, self.idx, self.on_card_goto)

    def on_card_goto(self, idx):
        self.idx = idx
        self.render()

    def destroy(self):
        """关闭刷题窗口时，刷新主界面统计"""
        master = self.master
        super().destroy()
        if hasattr(master, "refresh_stats"):
            master.refresh_stats()


class CardWindow(tk.Toplevel):
    """答题卡导航（支持滚动查看全部题目）"""
    def __init__(self, master, questions, cur, callback):
        super().__init__(master)
        self.callback = callback
        self.title("答题卡")
        self.configure(bg=BG)
        center_window(self, 780, 620)
        self.resizable(False, False)

        # 底部固定关闭按钮
        tk.Button(self, text="关闭", font=FONT_BTN, command=self.destroy,
                  bg="white", bd=1, relief=tk.SOLID).pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=8)

        # 滚动容器
        canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=(10, 0))
        sb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=(10, 0))
        inner = tk.Frame(canvas, bg=BG)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_inner(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(inner_id, width=canvas.winfo_width())
        inner.bind("<Configure>", on_inner)

        def on_wheel(e):
            canvas.yview_scroll(int(-e.delta / 120), "units")
        canvas.bind("<MouseWheel>", on_wheel)
        inner.bind("<MouseWheel>", on_wheel)

        cols = 8; rows = (len(questions) + cols - 1) // cols
        for c in range(cols):
            inner.columnconfigure(c, weight=1)
        res_map = master.results if isinstance(master, StudyWindow) else {}
        cur_row = (cur // cols) if 0 <= cur < len(questions) else 0
        for i, q in enumerate(questions):
            res = res_map.get(q.get("id"))
            if res == 1:
                bg, fg = GREEN, "white"          # 答对的题绿色
            elif res == 0:
                bg, fg = RED, "white"            # 答错的题红色
            elif i == cur:
                bg, fg = BLUE, "white"          # 未答的当前题蓝色高亮
            else:
                bg, fg = "white", FG
            btn = tk.Button(inner, text=str(i + 1), width=4, font=FONT, bd=1,
                            relief=tk.SOLID, bg=bg, fg=fg,
                            command=lambda x=i: self.goto(x))
            btn.grid(row=i // cols, column=i % cols, padx=2, pady=2)

        # 打开时滚动到当前题所在行
        if rows > 0:
            self.after(120, lambda: canvas.yview_moveto(min(1.0, cur_row / max(1, rows - 1))))

    def goto(self, idx):
        self.callback(idx)
        self.destroy()


class ExamWindow(tk.Toplevel):
    """模拟考试窗口"""
    def __init__(self, master, questions):
        super().__init__(master)
        self.questions = questions
        self.idx = 0
        self.answers = {}
        self.done = False
        self.time_left = 120 * 60
        self.timer_job = None

        self.title("模拟考试")
        center_window(self, 1020, 760)
        self.minsize(860, 600)
        self.configure(bg=BG)

        top = tk.Frame(self, bg=BLUE)
        top.pack(fill=tk.X)
        tk.Label(top, text="模拟考试", bg=BLUE, fg="white", font=FONT_BIG).pack(side=tk.LEFT, padx=16, pady=10)
        self.lb_timer = tk.Label(top, text="时间剩余：02:00:00", bg=BLUE, fg="#FFE08A", font=FONT_BIG)
        self.lb_timer.pack(side=tk.RIGHT, padx=16)
        self.lb_progress = tk.Label(top, text="第 1/{} 题".format(len(questions)), bg=BLUE, fg="white", font=FONT)
        self.lb_progress.pack(side=tk.RIGHT, padx=16)

        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=18, pady=12)

        self.txt_q = tk.Text(body, font=FONT, wrap=tk.WORD, bg="white", relief=tk.FLAT,
                             padx=12, pady=10, spacing3=4, height=10)
        self.txt_q.pack(fill=tk.BOTH, expand=True)
        self.txt_q.config(state=tk.DISABLED)

        self.ans_frame = tk.Frame(body, bg="white")
        self.ans_frame.pack(fill=tk.X, pady=(10, 0))

        bottom = tk.Frame(self, bg=BG)
        bottom.pack(fill=tk.X, padx=18, pady=(0, 14))
        for col in range(3):
            bottom.columnconfigure(col, weight=1)
        tk.Button(bottom, text="上一题", font=FONT_BTN, bg="white", fg=FG, bd=1, relief=tk.SOLID,
                  command=self.prev).grid(row=0, column=0, sticky="ew", padx=4)
        tk.Button(bottom, text="交卷评分", font=FONT_BTN, bg=RED, fg="white", bd=0,
                  command=self.finish).grid(row=0, column=1, sticky="ew", padx=4)
        tk.Button(bottom, text="下一题", font=FONT_BTN, bg=BLUE, fg="white", bd=0,
                  command=self.next).grid(row=0, column=2, sticky="ew", padx=4)

        self.render()
        self.tick()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        if not self.done:
            if messagebox.askyesno("退出考试", "考试尚未交卷，确定退出吗？", parent=self):
                self.stop_timer(); self.destroy()
        else:
            self.destroy()

    def stop_timer(self):
        if self.timer_job:
            self.after_cancel(self.timer_job)
            self.timer_job = None

    def tick(self):
        if self.done:
            return
        self.time_left -= 1
        h = self.time_left // 3600; m = self.time_left % 3600 // 60; s = self.time_left % 60
        self.lb_timer.config(text="时间剩余：{:02d}:{:02d}:{:02d}".format(h, m, s))
        if self.time_left <= 0:
            messagebox.showinfo("时间到", "考试时间到，自动交卷！", parent=self)
            self.finish()
            return
        self.timer_job = self.after(1000, self.tick)

    def clear_ans(self):
        for w in self.ans_frame.winfo_children():
            w.destroy()
        self.var = None

    def render(self):
        self.lb_progress.config(text="第 {}/{} 题".format(self.idx + 1, len(self.questions)))
        q = self.questions[self.idx]
        self.txt_q.config(state=tk.NORMAL)
        self.txt_q.delete("1.0", tk.END)
        self.txt_q.insert("1.0", "{}. {}\n【{}】".format(q["id"], q["q"], q_type_name(q)))
        self.txt_q.config(state=tk.DISABLED)
        self.clear_ans()
        saved = self.answers.get(q["id"])
        if q["type"] == "single":
            self.var = tk.StringVar(value=saved or "")
            letters = "ABCDEFGH"
            for i, opt in enumerate(q.get("opts", [])):
                opt_lb = opt if opt[:2].rstrip().endswith(")") else letters[i] + ") " + opt
                rb = tk.Radiobutton(self.ans_frame, text="  " + opt_lb, variable=self.var,
                                    value=letters[i], font=FONT, bg="white", anchor="w",
                                    activebackground=LIGHT_BLUE, padx=8, pady=3,
                                    wraplength=940, justify=tk.LEFT)
                rb.grid(row=i, column=0, sticky="ew")
        else:
            tk.Label(self.ans_frame, text="请输入答案：", font=FONT, bg="white",
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 2))
            self.var = tk.StringVar(value=str(saved or ""))
            self.ent = tk.Entry(self.ans_frame, textvariable=self.var, font=FONT)
            self.ent.grid(row=1, column=0, sticky="ew", padx=8)

    def current(self):
        return self.questions[self.idx]

    def get_ans(self, q):
        if q["type"] == "single":
            return self.var.get() if self.var else ""
        return self.var.get().strip() if self.var else ""

    def next(self):
        self.save_cur()
        if self.idx < len(self.questions) - 1:
            self.idx += 1
            self.render()

    def prev(self):
        self.save_cur()
        if self.idx > 0:
            self.idx -= 1
            self.render()

    def save_cur(self):
        q = self.current()
        a = self.get_ans(q)
        if a:
            self.answers[q["id"]] = a

    def finish(self):
        self.done = True
        self.save_cur()
        self.stop_timer()
        total = len(self.questions)
        right = 0
        wrong_list = []
        for q in self.questions:
            a = self.answers.get(q["id"], "")
            if q["type"] == "single":
                ok = a == q["ans"]
            else:
                key = answer_key(q["ans"])
                ok = bool(key and key in answer_key(a))
            if ok:
                right += 1
            else:
                wrong_list.append(q)
        total = max(len(self.questions), 1)
        score = right / total * 100
        ids = load_wrong_ids()
        for q in wrong_list:
            ids.add(q["id"])
        save_wrong_ids(ids)
        msg = "本次考试共 {} 题\n答对 {} 题，答错 {} 题\n评分：{:.1f} 分（百分制）\n\n错题已自动加入错题本，可返回主菜单进入错题本复习。".format(
            total, right, total - right, score)
        messagebox.showinfo("考试结果", msg, parent=self)
        self.destroy()


class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.questions = load_questions()
        self.progress = load_progress()   # 全局做题记录，跨会话保留
        self.title("题库刷题练习")
        center_window(self, 760, 580)
        self.resizable(False, False)
        self.configure(bg=BG)

        head = tk.Frame(self, bg=BLUE)
        head.pack(fill=tk.X)
        tk.Label(head, text="题库刷题练习", bg=BLUE, fg="white", font=("Microsoft YaHei", 18, "bold")).pack(pady=(26, 2))
        tk.Label(head, text="导入题库即可开始刷题", bg=BLUE, fg="#FFE08A", font=FONT).pack(pady=(0, 26))

        mid = tk.Frame(self, bg=BG)
        mid.pack(fill=tk.BOTH, expand=True, pady=18)
        s = len(self.questions)
        single = sum(1 for q in self.questions if q["type"] == "single")
        fill = s - single
        self.lb_bank = tk.Label(mid, text="题库统计：共 {} 题（单选/判断 {} 题，填空 {} 题）".format(s, single, fill),
                                bg=BG, fg=FG, font=FONT)
        self.lb_bank.pack(pady=6)
        wrong = len(load_wrong_ids())
        self.lb_wrong = tk.Label(mid, text="错题本：{} 题".format(wrong),
                                 bg=BG, fg=FG, font=FONT)
        self.lb_wrong.pack(pady=(0, 6))
        done = sum(1 for v in self.progress.values() if v == 1)
        self.lb_done = tk.Label(mid, text="已刷 {} 题，答对 {} 题".format(len(self.progress), done),
                                bg=BG, fg=("green" if self.progress else FG), font=FONT)
        self.lb_done.pack(pady=(0, 18))

        self.btn_area = tk.Frame(mid, bg=BG)
        self.btn_area.pack()

        def mk_btn(text, cmd):
            return tk.Button(self.btn_area, text=text, font=FONT_BTN, width=22,
                             bg="white", fg=FG, bd=1, relief=tk.SOLID, command=cmd,
                             activebackground=LIGHT_BLUE, pady=10)

        mk_btn("顺序刷题", lambda: self.study("order")).pack(pady=6)
        mk_btn("随机刷题", lambda: self.study("random")).pack(pady=6)
        mk_btn("错题本（复习错题）", lambda: self.study("wrong")).pack(pady=6)
        mk_btn("模拟考试", self.exam).pack(pady=6)
        mk_btn("导入题库", self.import_qbank).pack(pady=6)
        mk_btn("退出", self.destroy).pack(pady=6)

    def refresh_stats(self):
        """重新读取做题记录与错题本，刷新主界面统计（刷题窗口关闭 / 导入题库时调用）"""
        s = len(self.questions)
        single = sum(1 for q in self.questions if q["type"] == "single")
        self.lb_bank.config(text="题库统计：共 {} 题（单选/判断 {} 题，填空 {} 题）".format(s, single, s - single))
        done = sum(1 for v in self.progress.values() if v == 1)
        self.lb_wrong.config(text="错题本：{} 题".format(len(load_wrong_ids())))
        self.lb_done.config(text="已刷 {} 题，答对 {} 题".format(len(self.progress), done),
                            fg=("green" if self.progress else FG))

    def import_qbank(self):
        """导入自定义题库：选择 JSON 文件替换当前题库，旧题库自动备份"""
        path = filedialog.askopenfilename(
            title="选择题库 JSON 文件",
            filetypes=[("JSON 题库", "*.json"), ("所有文件", "*.*")],
            parent=self)
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("导入失败", "无法读取该 JSON 文件：{}".format(e), parent=self)
            return
        questions = data["questions"] if isinstance(data, dict) and "questions" in data else data
        ok, err = validate_bank(questions)
        if not ok:
            messagebox.showerror("导入失败", "题库格式不符合要求：\n{}".format(err), parent=self)
            return
        for i, q in enumerate(questions, 1):
            if "id" not in q:
                q["id"] = i
        if os.path.exists(TIKU_FILE):
            try:
                with open(TIKU_FILE, "r", encoding="utf-8") as f:
                    old = json.load(f)
                with open(TIKU_FILE + ".backup.json", "w", encoding="utf-8") as f:
                    json.dump(old, f, ensure_ascii=False)
            except Exception:
                pass
        with open(TIKU_FILE, "w", encoding="utf-8") as f:
            json.dump({"total": len(questions), "questions": questions}, f, ensure_ascii=False)
        wipe = messagebox.askyesno(
            "导入成功",
            "已导入 {} 题，原题库已备份为 tiku.backup.json。\n\n是否同时清空旧的做题记录和错题本？".format(len(questions)),
            parent=self)
        if wipe:
            self.progress = {}
            save_progress(self.progress)
            save_wrong_ids(set())
        self.questions = questions
        self.refresh_stats()
        messagebox.showinfo("完成", "当前题库已更新，共 {} 题。".format(len(self.questions)), parent=self)

    def study(self, mode):
        if mode == "order":
            qs = self.questions
        elif mode == "random":
            qs = random.sample(self.questions, len(self.questions))
        else:
            ids = load_wrong_ids()
            qs = [q for q in self.questions if q["id"] in ids]
            if not qs:
                messagebox.showinfo("错题本", "错题本还没有题目，加油！")
                return
        StudyWindow(self, qs, mode, {"order": "顺序刷题", "random": "随机刷题", "wrong": "错题本复习"}[mode])

    def exam(self):
        if len(self.questions) < 10:
            messagebox.showinfo("提示", "题库题目太少，暂不能模拟考试")
            return
        qs = random.sample(self.questions, min(40, len(self.questions)))
        ExamWindow(self, qs)


if __name__ == "__main__":
    ensure_tiku()
    if not os.path.exists(TIKU_FILE):
        print("错误：找不到题库文件 tiku.json，请通过主界面【导入题库】或将其与本程序放在同一目录。")
        input("按回车键退出...")
    else:
        app = MainApp()
        app.mainloop()
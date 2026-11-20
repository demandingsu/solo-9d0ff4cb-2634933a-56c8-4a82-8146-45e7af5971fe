"""Minimal HTML views (stdlib string formatting, escaped output)."""

from __future__ import annotations

from html import escape

from .archive import ArchiveSummary, FrameView
from .verify import VerifyReport


def _mc(value: int) -> str:
    return "%d m°C (%.3f °C)" % (value, value / 1000.0)


def _stored_text(kind: str, value: int) -> str:
    return "%s %d" % ("absolute" if kind == "absolute" else "delta", value)


_FRAME_FIELDS = {
    "missing_in_current": "现档缺少该帧",
    "unexpected_in_current": "现档多出该帧",
    "sampled_at": "采样时刻与原件不符",
    "base_seq": "基准引用与原件不符",
}

_REVISION_FIELDS = {
    "base_seq": "更正前基准引用",
    "new_base_seq": "更正后基准引用",
    "old_restored_mc": "更正前还原温度",
    "old_stored": "更正前存储值",
    "new_stored": "更正后存储值",
    "missing_frame": "原件无此帧",
    "missing_base": "原件无其基准帧",
}


STYLE = """
:root{color-scheme:light dark;--fg:#1c1c1e;--bg:#fafafa;--muted:#6b6b70;--line:#d8d8dc;
--accent:#0b62c4;--bad:#b3261e;--ok:#1e6b34;--warn:#8a5a00}
@media (prefers-color-scheme:dark){:root{--fg:#eaeaea;--bg:#17171a;--muted:#a0a0a8;
--line:#3a3a40;--accent:#6aa9ff;--bad:#ff8a80;--ok:#7fce93;--warn:#e0b050}}
*{box-sizing:border-box}
body{font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--fg);
background:var(--bg);margin:0;padding:24px}
main{max-width:960px;margin:0 auto}
h1{font-size:1.4rem;margin:0 0 4px}
h2{font-size:1.1rem;margin:24px 0 8px}
a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
.muted{color:var(--muted)} .small{font-size:.86rem}
table{border-collapse:collapse;width:100%;margin:8px 0}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;
vertical-align:top}
th{font-weight:600;color:var(--muted);font-size:.8rem;text-transform:uppercase;
letter-spacing:.03em}
tr.stale td{background:rgba(179,38,30,.08)}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
form.card{border:1px solid var(--line);border-radius:10px;padding:16px;margin:12px 0;
background:color-mix(in srgb,var(--bg) 92%, var(--fg) 8%)}
label{display:block;font-weight:600;margin:10px 0 4px}
input[type=text],input[type=number],input[type=file],select{width:100%;padding:8px;
border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);
font:inherit}
button{margin-top:14px;padding:9px 16px;border-radius:7px;border:0;
background:var(--accent);color:#fff;font:inherit;font-weight:600;cursor:pointer}
button:disabled{opacity:.5;cursor:not-allowed}
.notice{border-radius:8px;padding:10px 14px;margin:12px 0;border:1px solid}
.notice.ok{border-color:var(--ok);color:var(--ok)}
.notice.bad{border-color:var(--bad);color:var(--bad)}
.notice.warn{border-color:var(--warn);color:var(--warn)}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px;margin:8px 0}
.kv dt{color:var(--muted)} .kv dd{margin:0}
nav{margin-bottom:18px}
"""


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>%s</title><style>%s</style></head><body><main>%s</main></body></html>"
        % (escape(title), STYLE, body)
    )


def index_page(archives: list[ArchiveSummary], notice: str | None = None,
               notice_kind: str = "ok") -> str:
    parts = ["<h1>湖泊测温档案</h1>"]
    parts.append("<p class=\"muted\">上传记录仪 CSV，按帧序号查看还原温度并提交更正。</p>")
    if notice:
        parts.append("<div class=\"notice %s\">%s</div>" % (escape(notice_kind), escape(notice)))

    parts.append("<h2>导入记录仪 CSV</h2>")
    parts.append(
        "<form class=\"card\" method=\"post\" action=\"/archives\" enctype=\"multipart/form-data\">"
        "<label for=\"name\">档案名称</label>"
        "<input id=\"name\" name=\"name\" type=\"text\" required maxlength=\"120\""
        " placeholder=\"例如：北湖 2024 年 1 月\">"
        "<label for=\"file\">CSV 文件</label>"
        "<input id=\"file\" name=\"file\" type=\"file\" accept=\".csv,text/csv\" required>"
        "<p class=\"muted small\">列：<code>seq</code>、<code>sampled_at_utc</code>、"
        "<code>value_millidegrees_c</code>（整数毫摄氏度）、<code>kind</code>"
        "（absolute/delta）、<code>base_seq</code>（delta 时引用较早帧）。</p>"
        "<button type=\"submit\">上传并归档</button></form>"
    )

    parts.append("<h2>现有档案</h2>")
    if not archives:
        parts.append("<p class=\"muted\">还没有档案。</p>")
    else:
        rows = []
        for a in archives:
            rows.append(
                "<tr><td><a href=\"/archives/%d\">%s</a></td><td>%d</td><td class=\"mono small\">%s</td>"
                "<td class=\"small muted\">%s</td></tr>"
                % (a.id, escape(a.name), a.frame_count, escape(a.source_filename),
                   escape(a.created_at))
            )
        parts.append(
            "<table><thead><tr><th>档案</th><th>帧数</th><th>源文件</th><th>导入时间</th></tr>"
            "</thead><tbody>%s</tbody></table>" % "".join(rows)
        )
    return _page("湖泊测温档案", "".join(parts))


def _fmt_opt(value) -> str:
    return "—" if value is None else str(value)


def archive_page(archive: ArchiveSummary, frames: list[FrameView],
                 notice: str | None = None, notice_kind: str = "ok",
                 missing_seq: int | None = None) -> str:
    parts = [
        "<nav><a href=\"/\">← 全部档案</a></nav>",
        "<h1>%s</h1>" % escape(archive.name),
        "<div class=\"kv\"><dt>源文件</dt><dd class=\"mono\">%s</dd>"
        "<dt>帧数</dt><dd>%d</dd>"
        "<dt>导入时间</dt><dd class=\"mono\">%s</dd></div>"
        % (escape(archive.source_filename), archive.frame_count, escape(archive.created_at)),
        "<p><a href=\"/archives/%d/download.csv\">下载 CSV（整份同一已提交状态）</a></p>"
        % archive.id,
    ]
    if notice:
        parts.append("<div class=\"notice %s\">%s</div>" % (escape(notice_kind), escape(notice)))
    if missing_seq is not None:
        parts.append("<div class=\"notice bad\">本档案没有序号为 %d 的帧。</div>"
                     % missing_seq)
    parts.append("<p class=\"muted small\">点击帧序号进入单帧页面查看还原温度并提交更正。"
                 "绝对帧的存储值等于还原温度；相对帧的存储值是相对更早基准帧的差值。"
                 "更正基准帧不会改动其他帧的还原温度和基准引用。</p>")
    parts.append(
        "<form class=\"card\" method=\"get\" action=\"/archives/%d/lookup\">"
        "<label for=\"seq\">按帧序号查还原温度</label>"
        "<input id=\"seq\" name=\"seq\" type=\"number\" min=\"0\" step=\"1\" required"
        " placeholder=\"输入帧序号\">"
        "<button type=\"submit\">查看该帧</button></form>" % archive.id
    )

    parts.append("<h2>核验现档</h2>")
    parts.append(
        "<form class=\"card\" method=\"post\" action=\"/archives/%d/verify\""
        " enctype=\"multipart/form-data\">"
        "<label for=\"original\">首次入档的记录仪 CSV</label>"
        "<input id=\"original\" name=\"file\" type=\"file\" accept=\".csv,text/csv\" required>"
        "<p class=\"muted small\">从原始读数与历次更正出发，核对现档的帧号、采样时刻、"
        "基准引用、每笔更正的还原温度与存储值，以及重建温度。核验只读，不写入任何数据，"
        "期间可以继续更正。</p>"
        "<button type=\"submit\">开始核验</button></form>" % archive.id
    )

    trs = []
    for f in frames:
        base_cell = _fmt_opt(f.base_seq)
        if f.base_seq is not None:
            base_cell = "<a href=\"/archives/%d/frames/%d\">%d</a>" % (
                archive.id, f.base_seq, f.base_seq)
        trs.append(
            "<tr><td><a href=\"/archives/%d/frames/%d\">%d</a></td>"
            "<td class=\"mono\">%s</td><td class=\"mono\">%s</td>"
            "<td>%s</td><td class=\"mono\">%s</td></tr>"
            % (archive.id, f.seq, f.seq, escape(f.sampled_at),
               escape("%s %d" % (f.stored_kind, f.stored_mc)), base_cell,
               escape(_mc(f.restored_mc)))
        )
    parts.append(
        "<table><thead><tr><th>序号</th><th>UTC 采样时间</th><th>存储形式与值</th>"
        "<th>基准帧</th><th>还原温度</th></tr></thead><tbody>%s</tbody></table>"
        % "".join(trs)
    )
    return _page(archive.name, "".join(parts))


def frame_page(archive: ArchiveSummary, frame: FrameView, base: FrameView | None,
               referrers: list[FrameView],
               notice: str | None = None, notice_kind: str = "ok") -> str:
    parts = [
        "<nav><a href=\"/\">全部档案</a> · <a href=\"/archives/%d\">%s</a></nav>"
        % (archive.id, escape(archive.name)),
        "<h1>帧 %d</h1>" % frame.seq,
        "<div class=\"kv\"><dt>UTC 采样时间</dt><dd class=\"mono\">%s</dd>"
        "<dt>还原温度</dt><dd class=\"mono\"><strong>%s</strong></dd>"
        "<dt>存储形式</dt><dd class=\"mono\">%s %d</dd>"
        "<dt>基准帧</dt><dd>%s</dd></div>"
        % (
            escape(frame.sampled_at), escape(_mc(frame.restored_mc)),
            escape(frame.stored_kind), frame.stored_mc,
            ("<a href=\"/archives/%d/frames/%d\">帧 %d</a>（%s）"
             % (archive.id, base.seq, base.seq, escape(_mc(base.restored_mc))))
            if base is not None else "—",
        ),
    ]
    if notice:
        parts.append("<div class=\"notice %s\">%s</div>" % (escape(notice_kind), escape(notice)))
    if frame.base_seq is not None and base is not None:
        parts.append(
            "<div class=\"notice warn\">本帧存储的是相对帧 %d 的差值。更正帧 %d 的还原温度后，"
            "本帧的还原温度与基准引用保持原样，只有存储差值随基准变化。</div>"
            % (base.seq, base.seq)
        )
    if referrers:
        parts.append("<div class=\"notice warn\">以下帧以本帧为基准：%s。更正本帧不会改动"
                     "它们的还原温度和基准引用；只有它们的存储差值随本帧变化，下载时按新差值"
                     "导出。</div>" % escape("、".join(str(r.seq) for r in referrers)))

    parts.append("<h2>提交更正</h2>")
    parts.append(
        "<form class=\"card\" method=\"post\" action=\"/archives/%d/frames/%d/correct\">"
        "<input type=\"hidden\" name=\"seen_restored_mc\" value=\"%d\">"
        "<label for=\"new_restored_mc\">更正后的还原温度（整数毫摄氏度）</label>"
        "<input id=\"new_restored_mc\" name=\"new_restored_mc\" type=\"number\" step=\"1\""
        " required value=\"%d\">"
        "<p class=\"muted small\">提交前请核对：本页显示的温度是 <span class=\"mono\">%s</span>。"
        "若在提交前该帧的还原温度已被他人更正，提交会被拒绝并保留现档。</p>"
        "<button type=\"submit\">提交更正</button></form>"
        % (archive.id, frame.seq, frame.restored_mc, frame.restored_mc,
           escape(_mc(frame.restored_mc)))
    )
    return _page("帧 %d" % frame.seq, "".join(parts))


def _issue_value(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, tuple):
        return _stored_text(value[0], value[1])
    return str(value)


def verify_page(report: VerifyReport, notice: str | None = None,
                notice_kind: str = "ok") -> str:
    parts = [
        "<nav><a href=\"/\">全部档案</a> · <a href=\"/archives/%d\">%s</a></nav>"
        % (report.archive_id, escape(report.archive_name)),
        "<h1>核验报告</h1>",
        "<div class=\"kv\">"
        "<dt>档案</dt><dd>%s</dd>"
        "<dt>原件</dt><dd class=\"mono\">%s</dd>"
        "<dt>报告基准</dt><dd>同一已提交状态，末笔更正编号 <span class=\"mono\">%s</span>"
        "（共 %d 笔）</dd>"
        "<dt>帧数</dt><dd>原件 %d · 现档 %d</dd>"
        "<dt>核验方式</dt><dd>只读；核验期间其他提交的更正不计入本报告</dd>"
        "</div>" % (
            escape(report.archive_name),
            escape(report.original_filename or "（未记录文件名）"),
            "—" if report.last_revision_id is None else str(report.last_revision_id),
            report.revision_count, report.original_frame_count,
            report.current_frame_count,
        ),
    ]
    if notice:
        parts.append("<div class=\"notice %s\">%s</div>" % (escape(notice_kind), escape(notice)))

    if report.passed:
        parts.append("<div class=\"notice ok\"><strong>核验通过。</strong>"
                     "现档的帧号、采样时刻、基准引用、历次更正与重建温度均与原件相符。</div>")
    elif not report.structure_ok:
        parts.append("<div class=\"notice bad\"><strong>核验未通过：原件与现档的帧结构不符。</strong>"
                     "见下方相关帧号。</div>")
    elif not report.revisions_ok:
        fm = report.first_mismatch
        parts.append(
            "<div class=\"notice bad\"><strong>核验未通过：第 %d 笔更正（帧 %d）对不上。</strong>"
            "即使现档最终读数吻合，账目也有误。</div>" % (fm.revision_id, fm.seq))
    else:
        parts.append("<div class=\"notice bad\"><strong>核验未通过：重建温度与现档不符。</strong>"
                     "见下方帧列表。</div>")

    # 1. structure
    parts.append("<h2>一、原件与现档的帧结构</h2>")
    if report.structure_ok:
        parts.append("<p class=\"notice ok\">帧号、采样时刻、基准引用全部相符。</p>")
    else:
        rows = []
        for iss in report.frame_issues:
            rows.append(
                "<tr class=\"stale\"><td>%d</td><td>%s</td><td class=\"mono\">%s</td>"
                "<td class=\"mono\">%s</td></tr>"
                % (iss.seq, escape(_FRAME_FIELDS.get(iss.field, iss.field)),
                   escape(_issue_value(iss.original)),
                   escape(_issue_value(iss.current)))
            )
        parts.append(
            "<table><thead><tr><th>帧号</th><th>问题</th><th>原件</th><th>现档</th></tr>"
            "</thead><tbody>%s</tbody></table>" % "".join(rows))

    # 2. revisions
    parts.append("<h2>二、历次更正的账目</h2>")
    if not report.revision_checks:
        parts.append("<p class=\"muted\">该档案还没有更正记录。</p>")
    else:
        if report.revisions_ok:
            parts.append("<p class=\"notice ok\">%d 笔更正的基准引用、还原温度与存储值全部相符。</p>"
                         % len(report.revision_checks))
        else:
            fm = report.first_mismatch
            parts.append(
                "<p class=\"notice bad\">第一笔对不上的更正：编号 <span class=\"mono\">%d</span>"
                "（帧 %d）。</p>" % (fm.revision_id, fm.seq))
        rows = []
        for chk in report.revision_checks:
            base_txt = "—"
            if chk.base_seq is not None:
                base_txt = "帧 %d（当时还原 %s）" % (
                    chk.base_seq,
                    "—" if chk.base_restored_mc is None
                    else _mc(chk.base_restored_mc))
            old_exp = "—" if chk.expected_old_stored is None else \
                _stored_text(*chk.expected_old_stored)
            new_exp = "—" if chk.expected_new_stored is None else \
                _stored_text(*chk.expected_new_stored)
            if chk.ok:
                verdict = "<span style=\"color:var(--ok)\">相符</span>"
                detail = ""
            else:
                verdict = "<span style=\"color:var(--bad)\">不符</span>"
                detail = "；".join(
                    "%s：应为 %s，账记 %s" % (
                        _REVISION_FIELDS.get(i.field, i.field),
                        _issue_value(i.expected), _issue_value(i.recorded))
                    for i in chk.issues)
                detail = "<br><span class=\"small\">%s</span>" % escape(detail)
            rows.append(
                "<tr%s><td class=\"mono\">%d</td><td><a href=\"/archives/%d/frames/%d\">%d</a></td>"
                "<td class=\"small\">%s</td>"
                "<td class=\"mono\">%s<br>→ %s</td>"
                "<td class=\"mono\">%s<br>→ %s</td>"
                "<td>%s%s</td></tr>"
                % (" class=\"stale\"" if not chk.ok else "",
                   chk.revision_id, report.archive_id, chk.seq, chk.seq, escape(base_txt),
                   escape(_mc(chk.old_restored_mc)), escape(_mc(chk.new_restored_mc)),
                   escape(old_exp), escape(new_exp), verdict, detail)
            )
        parts.append(
            "<table><thead><tr><th>更正编号</th><th>帧</th><th>基准（当时）</th>"
            "<th>还原温度 前→后</th><th>存储值 前→后（应）</th><th>结论</th></tr>"
            "</thead><tbody>%s</tbody></table>" % "".join(rows))

    # 3. reconstructed restored values
    parts.append("<h2>三、重建温度与现档</h2>")
    if not report.restored_checked:
        if not report.structure_ok:
            parts.append("<p class=\"muted\">帧结构与原件不符，未进入重建温度核对。</p>")
        else:
            parts.append("<p class=\"muted\">更正账目有误，未进入重建温度核对。</p>")
    elif not report.restored_issues:
        parts.append("<p class=\"notice ok\">重建温度与现档逐帧相符。</p>")
    else:
        rows = []
        for iss in report.restored_issues:
            rows.append(
                "<tr class=\"stale\"><td><a href=\"/archives/%d/frames/%d\">%d</a></td>"
                "<td class=\"mono\">%s</td><td class=\"mono\">%s</td>"
                "<td class=\"mono\">%d</td></tr>"
                % (report.archive_id, iss.seq, iss.seq, escape(_mc(iss.reconstructed_mc)),
                   escape(_mc(iss.current_mc)),
                   iss.current_mc - iss.reconstructed_mc)
            )
        parts.append(
            "<table><thead><tr><th>帧号</th><th>重建温度</th><th>现档温度</th>"
            "<th>差（m°C）</th></tr></thead><tbody>%s</tbody></table>" % "".join(rows))

    return _page("核验报告 · %s" % report.archive_name, "".join(parts))


def error_page(status: int, message: str) -> str:
    return _page("错误 %d" % status, "<h1>%d</h1><div class=\"notice bad\">%s</div>"
                 "<p><a href=\"/\">← 返回全部档案</a></p>"
                 % (status, escape(message)))


import html
import re
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import requests
from requests.auth import HTTPBasicAuth

# ══════════════════════════════════════════════════════════════════════════════
#  PAGE CONFIG — must be the very first Streamlit call
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="CBM 2.0 · DevOps Overview",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Connection Details ─────────────────────────────────────────────────────────
ORG_URL = "https://dev.azure.com/vgroupframework"
PROJECT = "SeaTec - CBM"
PAT = st.secrets["AZURE_PAT"]
AUTH = HTTPBasicAuth('', PAT)

# ── State Configuration ────────────────────────────────────────────────────────
STATE_CONFIG = {
    "Available for UAT": {"color": "#0f766e", "bg": "#ecfeff", "icon": "●"},
    "In Progress": {"color": "#b45309", "bg": "#fff7ed", "icon": "●"},
    "Approved": {"color": "#2563eb", "bg": "#eff6ff", "icon": "●"},
    "Approved for Analysis": {"color": "#2563eb", "bg": "#eff6ff", "icon": "●"},
    "Analysis In Progress": {"color": "#b45309", "bg": "#fff7ed", "icon": "●"},
    "Prototype": {"color": "#7c3aed", "bg": "#f5f3ff", "icon": "●"},
    "Ready for Review": {"color": "#0f766e", "bg": "#ecfeff", "icon": "●"},
    "Awaiting Feedback": {"color": "#b42318", "bg": "#fef3f2", "icon": "●"},
    "Working on Feedback": {"color": "#b45309", "bg": "#fff7ed", "icon": "●"},
    "Done": {"color": "#2563eb", "bg": "#eff6ff", "icon": "●"},
    "Blocked": {"color": "#b42318", "bg": "#fef3f2", "icon": "●"},
    "To Do": {"color": "#475569", "bg": "#f8fafc", "icon": "●"},
}

def get_state_cfg(state):
    return STATE_CONFIG.get(state, {"color": "#64748b", "bg": "#f8fafc", "icon": "●"})


def render_html_fragment(html: str, height: int = 220, scrolling: bool = False):
    components.html(html, height=height, scrolling=scrolling)


# ── Data Processing ────────────────────────────────────────────────────────────
def clean_html_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(
        r'(?i)<a[^>]*href=["\'](["\']+)["\'][^>]*>(.*?)</a>',
        lambda m: f'[{m.group(2)}]({m.group(1)})',
        text,
        flags=re.DOTALL,
    )
    text = re.sub(r'(?i)<(?:b|strong)[^>]*>', '**', text)
    text = re.sub(r'(?i)</(?:b|strong)>', '**', text)
    text = re.sub(r'(?i)<(?:i|em)[^>]*>', '*', text)
    text = re.sub(r'(?i)</(?:i|em)>', '*', text)
    block_tags = r'(p|div|h[1-6]|section|article|header|footer|blockquote|tr|td|th|li|ul|ol)'
    text = re.sub(fr'(?i)</?{block_tags}[^>]*>', '\n', text)
    text = re.sub(r'(?i)<li[^>]*>', '\n- ', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = '\n'.join(line.rstrip() for line in text.splitlines())
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip('\n ')
    return text


@st.cache_data(ttl=300, show_spinner=False)
def get_work_item_comments(work_item_id):
    url = f"{ORG_URL}/{PROJECT}/_apis/wit/workitems/{work_item_id}/comments?api-version=7.1-preview.3"
    response = requests.get(url, auth=AUTH)
    response.raise_for_status()
    comments = response.json()
    result = []
    for c in comments.get('comments', []):
        result.append({
            'text': clean_html_text(c['text']),
            'author': c.get('createdBy', {}).get('displayName', 'Unknown'),
            'date': c.get('createdDate', 'Unknown date'),
        })
    return result


@st.cache_data(ttl=300, show_spinner=False)
def get_board_work_items():
    wi_query = {
        "query": (
            f"SELECT [System.Id] FROM WorkItems "
            f"WHERE [System.TeamProject] = '{PROJECT}' "
            f"AND [System.WorkItemType] = 'User Story' "
            f"AND [System.State] <> 'Removed' "
            f"AND [System.AreaPath] = 'SeaTec - CBM\\CBM 2.0'"
        )
    }
    query_url = f"{ORG_URL}/{PROJECT}/_apis/wit/wiql?api-version=7.1-preview.2"
    query_res = requests.post(query_url, json=wi_query, auth=AUTH)
    query_res.raise_for_status()
    ids = [item['id'] for item in query_res.json()['workItems']]
    if not ids:
        return []
    all_items = []
    batch_size = 200
    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i:i + batch_size]
        ids_string = ",".join(map(str, batch_ids))
        details_url = (
            f"{ORG_URL}/{PROJECT}/_apis/wit/workitems"
            f"?ids={ids_string}&$expand=all&api-version=7.1-preview.3"
        )
        details_res = requests.get(details_url, auth=AUTH)
        details_res.raise_for_status()
        all_items.extend(details_res.json()['value'])
    return all_items


@st.cache_data(ttl=300, show_spinner="⏳ Loading work items from Azure DevOps...")
def load_dashboard_data():
    all_items = get_board_work_items()
    comments_by_id = {}
    title_by_id = {}
    data = []
    for item in all_items:
        fields = item.get('fields', {})
        title = fields.get('System.Title', 'No Title')
        board_column = fields.get('System.BoardColumn') or 'Unknown'
        comments = get_work_item_comments(item['id'])
        comments_by_id[item['id']] = comments
        trimmed_title = title.split('-')[-1].strip()
        title_by_id[item['id']] = trimmed_title
        relations = item.get('relations', [])
        attachments_count = sum(
            1 for rel in relations if rel.get('rel') == 'AttachedFile'
        )
        data.append({
            "ID": item['id'],
            "Title": trimmed_title,
            "State": board_column,
            "Comments": len(comments),
            "Attachments": attachments_count,
        })
    df_res = pd.DataFrame(data)
    df_res = df_res[~df_res['State'].isin(['New', 'Unknown'])].reset_index(drop=True)
    return df_res, comments_by_id, title_by_id


# ── Response Time Analysis Logic ───────────────────────────────────────────────
def get_party(author_name):
    author_lower = author_name.lower()
    if any(name in author_lower for name in ["vinita", "madhuja"]):
        return "Pii"
    elif "terence" in author_lower or "seatec" in author_lower:
        return "SeaTec"
    return "Other"


def analyze_comment_turnarounds(df, comments_by_id, title_by_id):
    turnaround_responses = []

    for item_id, comments in comments_by_id.items():
        if len(comments) < 2:
            continue

        parsed_comments = []
        for c in comments:
            try:
                dt = datetime.fromisoformat(c['date'].replace('Z', '+00:00'))
                parsed_comments.append({'author': c['author'], 'date': dt, 'text': c['text']})
            except Exception:
                continue

        parsed_comments.sort(key=lambda x: x['date'])

        for i in range(1, len(parsed_comments)):
            prev = parsed_comments[i - 1]
            curr = parsed_comments[i]

            prev_party = get_party(prev['author'])
            curr_party = get_party(curr['author'])

            if prev_party != "Other" and curr_party != "Other" and prev_party != curr_party:
                delay_days = round((curr['date'] - prev['date']).total_seconds() / 86400.0, 1)

                if delay_days > 5.0:
                    title = title_by_id.get(item_id, f"Card #{item_id}")
                    turnaround_responses.append({
                        "ID": item_id,
                        "Title": title,
                        "Card Label": f"#{item_id} - {title[:32]}...",
                        "Days": delay_days,
                        "Responding Party": curr_party,
                        "Prompted By": prev_party,
                        "Initial Author": prev['author'],
                        "Respondent": curr['author'],
                        "Response Date": curr['date'].strftime('%b %d, %Y'),
                    })

    return pd.DataFrame(turnaround_responses)


# ── UI Helpers & CSS ───────────────────────────────────────────────────────────

def local_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

        html, body, [class*="css"], [class*="st-"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        }

        [data-testid="stAppViewContainer"] {
            background-color: #ffffff !important;
        }

        [data-testid="stHeader"] {
            background-color: #ffffff !important;
            border-bottom: 1px solid #e7ecf3;
        }

        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 2rem !important;
            max-width: 1420px !important;
        }

        h1, h2, h3, h4, h5, h6 {
            color: #0f172a !important;
            font-weight: 700 !important;
        }

        div[data-testid="stMarkdownContainer"] p {
            font-size: 15px !important;
            line-height: 1.65 !important;
            color: #475569 !important;
        }

        [data-testid="stRadio"] fieldset {
            border: none !important;
        }

        [data-testid="stRadio"] > div {
            display: flex !important;
            flex-direction: row !important;
            gap: 8px !important;
            flex-wrap: wrap !important;
            align-items: center !important;
        }

        [data-testid="stRadio"] > div > label {
            background: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 999px !important;
            padding: 6px 14px !important;
            cursor: pointer !important;
            transition: all 0.2s ease !important;
            color: #475569 !important;
            font-size: 13px !important;
            font-weight: 600 !important;
        }

        [data-testid="stRadio"] > div > label:hover {
            border-color: #2f5edb !important;
            color: #0f172a !important;
        }

        [data-testid="stRadio"] > div > label:has(input:checked) {
            background: #eef4ff !important;
            border-color: #2f5edb !important;
            color: #2f5edb !important;
        }

        [data-testid="stRadio"] > div > label > div:first-child {
            display: none !important;
        }

        [data-testid="stSelectbox"] label {
            color: #0f172a !important;
            font-weight: 600 !important;
        }
        [data-testid="stSelectbox"] > div > div {
            background-color: #ffffff !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 10px !important;
            color: #0f172a !important;
        }

        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: #f1f5f9; }
        ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
        </style>
    """, unsafe_allow_html=True)


def render_header():
    render_html_fragment("""
        <div style="
            background: linear-gradient(135deg, #ffffff 0%, #f8fafc 55%, #f2f6ff 100%);
            border: 1px solid #e7ecf3;
            border-radius: 20px;
            padding: 26px 30px;
            margin-bottom: 24px;
            position: relative;
            font-family: Inter, sans-serif;
            box-shadow: 0 4px 20px rgba(15, 23, 42, 0.04);
        ">
            <div style="display: flex; align-items: center; gap: 16px;">
                <div style="
                    width: 52px; height: 52px;
                    background: #eef4ff;
                    border: 1px solid #cfe0ff;
                    border-radius: 14px;
                    display: flex; align-items: center; justify-content: center;
                    font-size: 22px; font-weight: 800; color: #2f5edb;
                    flex-shrink: 0;
                ">CB</div>
                <div>
                    <div style="font-size: 24px; font-weight: 800; color: #0f172a; letter-spacing: -0.5px;">
                        CBM 2.0 DevOps Overview
                    </div>
                    <div style="font-size: 13px; color: #64748b; margin-top: 4px; font-weight: 500;">
                        Azure DevOps &nbsp;&bull;&nbsp; SeaTec &#8211; CBM 2.0 &nbsp;&bull;&nbsp; User Stories
                    </div>
                </div>
            </div>
        </div>
    """, height=130)


def render_kpi_cards(state_list, total_count, selected_state):
    cards = []

    is_total_active = (selected_state is None)
    cards.append(f"""
        <div style="
            background: #ffffff;
            border: 1px solid #e7ecf3;
            border-left: 4px solid #2f5edb;
            border-radius: 14px;
            padding: 18px 16px;
            min-height: 110px;
            box-shadow: {'0 8px 20px rgba(15, 23, 42, 0.06)' if is_total_active else '0 2px 8px rgba(15, 23, 42, 0.03)'};
        ">
            <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:#2f5edb; margin-bottom:8px;"></span>
            <div style="font-size:32px; font-weight:800; color:#0f172a; line-height:1; margin-bottom:6px;">{total_count}</div>
            <div style="font-size:12px; color:#64748b; font-weight:600;">Total Stories</div>
        </div>
    """)

    for row in state_list:
        state = row['State']
        count = row['count']
        cfg = get_state_cfg(state)
        is_active = (selected_state == state)
        cards.append(f"""
            <div style="
                background: #ffffff;
                border: 1px solid #e7ecf3;
                border-left: 4px solid {cfg['color']};
                border-radius: 14px;
                padding: 18px 16px;
                min-height: 110px;
                box-shadow: {'0 8px 20px rgba(15, 23, 42, 0.06)' if is_active else '0 2px 8px rgba(15, 23, 42, 0.03)'};
            ">
                <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:{cfg['color']}; margin-bottom:8px;"></span>
                <div style="font-size:32px; font-weight:800; color:#0f172a; line-height:1; margin-bottom:6px;">{count}</div>
                <div style="font-size:12px; color:#64748b; font-weight:600;">{html.escape(state)}</div>
            </div>
        """)

    render_html_fragment(
        f'<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); gap:12px; margin-bottom:20px;">{"".join(cards)}</div>',
        height=160,
    )


def build_comment_popup_html(comments_list, is_top_row=False):
    popup_class = "comment-tooltip-popup popup-down" if is_top_row else "comment-tooltip-popup popup-up"

    if not comments_list:
        return f"""
            <div class="{popup_class}">
                <div style="font-size:12px; font-weight:600; color:#64748b; text-align:center;">No comments yet</div>
            </div>
        """

    comments_html = ""
    for idx, c in enumerate(sorted(comments_list, key=lambda x: x['date']), 1):
        author = html.escape(c.get('author', 'Unknown'))
        body = html.escape(c.get('text', '')).replace('\n', '<br>')
        try:
            date_obj = datetime.fromisoformat(c['date'].replace('Z', '+00:00'))
            formatted_date = date_obj.strftime('%b %d, %I:%M %p')
        except Exception:
            formatted_date = html.escape(c.get('date', ''))

        comments_html += f"""
            <div style="border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; margin-bottom: 8px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                    <span style="font-size:12px; font-weight:700; color:#0f172a;">#{idx} {author}</span>
                    <span style="font-size:10px; color:#64748b;">{formatted_date}</span>
                </div>
                <div style="font-size:12px; color:#334155; line-height:1.4;">{body}</div>
            </div>
        """

    return f"""
        <div class="{popup_class}">
            <div style="font-size:12px; font-weight:700; color:#2f5edb; margin-bottom:8px; border-bottom:1px solid #cbd5e1; padding-bottom:4px;">
                💬 Discussion History
            </div>
            {comments_html}
        </div>
    """


def render_stories_table(table_df, comments_by_id):
    rows_html = ""
    icon_map = {
        "🧪": "&#129514;", "🔄": "&#128260;", "✅": "&#9989;",
        "🚫": "&#128683;", "📋": "&#128203;", "🆕": "&#127373;", "•": "&bull;",
    }
    for row_idx, (_, row) in enumerate(table_df.iterrows()):
        item_id = int(row["ID"])
        state = row['State']
        cfg = get_state_cfg(state)
        icon_html = icon_map.get(cfg['icon'], cfg['icon'])
        
        badge = (
            f'<span style="display:inline-flex; align-items:center; gap:5px; border-radius:20px; padding:3px 11px; font-size:11px; font-weight:700; white-space:nowrap; border:1px solid {cfg["color"]}40; color:{cfg["color"]}; background:{cfg["bg"]};">'
            f'{icon_html} {html.escape(state)}</span>'
        )
        id_html = f'<span style="display:inline-block; background:#f8fafc; color:#334155; border:1px solid #e2e8f0; border-radius:6px; padding:2px 8px; font-size:11px; font-weight:700;">#{item_id}</span>'

        # Determine popup direction so popups in upper rows drop DOWN and lower rows pop UP
        is_upper_half = (row_idx < len(table_df) / 2)
        popup_class = "comment-tooltip-popup popup-down" if is_upper_half else "comment-tooltip-popup popup-up"

        comments_list = comments_by_id.get(item_id, [])
        
        if not comments_list:
            popup_layer = f'<div class="{popup_class}"><div style="font-size:12px; font-weight:600; color:#64748b; text-align:center;">No comments yet</div></div>'
        else:
            comments_inner = ""
            for idx_c, c in enumerate(sorted(comments_list, key=lambda x: x['date']), 1):
                author = html.escape(c.get('author', 'Unknown'))
                body = html.escape(c.get('text', '')).replace('\n', '<br>')
                try:
                    date_obj = datetime.fromisoformat(c['date'].replace('Z', '+00:00'))
                    formatted_date = date_obj.strftime('%b %d, %I:%M %p')
                except Exception:
                    formatted_date = html.escape(c.get('date', ''))

                comments_inner += f'''
                    <div style="border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; margin-bottom: 8px;">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                            <span style="font-size:12px; font-weight:700; color:#0f172a;">#{idx_c} {author}</span>
                            <span style="font-size:10px; color:#64748b;">{formatted_date}</span>
                        </div>
                        <div style="font-size:12px; color:#334155; line-height:1.4;">{body}</div>
                    </div>
                '''
            popup_layer = f'''
                <div class="{popup_class}">
                    <div style="font-size:12px; font-weight:700; color:#2f5edb; margin-bottom:8px; border-bottom:1px solid #cbd5e1; padding-bottom:4px;">
                        💬 Discussion History
                    </div>
                    {comments_inner}
                </div>
            '''

        comments_count = int(row["Comments Count"])

        comments_html = f'''
            <div class="comment-tooltip-container" onclick="toggleCommentPopup(event, this)">
                <span class="comment-trigger-btn" style="font-size:12px; color:#2f5edb; font-weight:700; display:inline-flex; align-items:center; gap:4px; padding:4px 10px; border-radius:6px; background:#eef4ff; border:1px solid #cfe0ff; user-select:none; cursor:pointer;">
                    &#128172; {comments_count}
                </span>
                {popup_layer}
            </div>
        '''

        attach_html = f'<span style="font-size:12px; color:#475569; font-weight:600; display:inline-flex; align-items:center; gap:4px;">&#128206; {int(row["Attachments Count"])}</span>'

        rows_html += f'''
            <tr>
                <td style="padding:13px 16px; border-bottom:1px solid #f1f5f9; vertical-align:middle;">{id_html}</td>
                <td style="padding:13px 16px; border-bottom:1px solid #f1f5f9; color:#0f172a; font-weight:600; font-size:14px; max-width:420px; word-break:break-word; vertical-align:middle;">
                    {html.escape(str(row['Title']))}
                </td>
                <td style="padding:13px 16px; border-bottom:1px solid #f1f5f9; vertical-align:middle;">{badge}</td>
                <td style="padding:13px 16px; border-bottom:1px solid #f1f5f9; text-align:center; vertical-align:middle; font-size:13px; position:relative;">{comments_html}</td>
                <td style="padding:13px 16px; border-bottom:1px solid #f1f5f9; text-align:center; vertical-align:middle; font-size:13px;">{attach_html}</td>
            </tr>
        '''

    render_html_fragment(f'''
        <style>
        .comment-tooltip-container {{
            position: relative;
            display: inline-block;
        }}
        .comment-tooltip-popup {{
            display: none;
            position: absolute;
            right: 0;
            width: 310px;
            max-height: 220px;
            overflow-y: auto;
            background: #ffffff;
            border: 1px solid #cbd5e1;
            border-radius: 12px;
            padding: 12px;
            box-shadow: 0 10px 25px rgba(15, 23, 42, 0.2);
            z-index: 99999;
            text-align: left;
        }}
        .comment-tooltip-popup.active {{
            display: block !important;
        }}
        .popup-up {{ bottom: 100%; margin-bottom: 6px; }}
        .popup-down {{ top: 100%; margin-top: 6px; }}
        </style>

        <div style="background:#ffffff; border:1px solid #e7ecf3; border-radius:16px; box-shadow:0 4px 16px rgba(15, 23, 42, 0.03); height:480px; overflow-y:auto; position:relative;">
            <table style="width:100%; border-collapse:collapse; font-size:14px;">
                <thead style="position: sticky; top: 0; z-index: 1000;">
                    <tr>
                        <th style="background:#f8fafc; color:#475569; font-weight:700; font-size:11px; letter-spacing:1.2px; text-transform:uppercase; padding:13px 16px; text-align:left; border-bottom:1px solid #e2e8f0; width:70px;">ID</th>
                        <th style="background:#f8fafc; color:#475569; font-weight:700; font-size:11px; letter-spacing:1.2px; text-transform:uppercase; padding:13px 16px; text-align:left; border-bottom:1px solid #e2e8f0;">Title</th>
                        <th style="background:#f8fafc; color:#475569; font-weight:700; font-size:11px; letter-spacing:1.2px; text-transform:uppercase; padding:13px 16px; text-align:left; border-bottom:1px solid #e2e8f0; width:170px;">Board Column</th>
                        <th style="background:#f8fafc; color:#475569; font-weight:700; font-size:11px; letter-spacing:1.2px; text-transform:uppercase; padding:13px 16px; text-align:center; border-bottom:1px solid #e2e8f0; width:100px;">Comments</th>
                        <th style="background:#f8fafc; color:#475569; font-weight:700; font-size:11px; letter-spacing:1.2px; text-transform:uppercase; padding:13px 16px; text-align:center; border-bottom:1px solid #e2e8f0; width:110px;">Attachments</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
        </div>

        <script>
        function toggleCommentPopup(event, container) {{
            event.stopPropagation();
            const popup = container.querySelector('.comment-tooltip-popup');
            if (!popup) return;
            
            const isOpen = popup.classList.contains('active');
            
            // Close all open comment popups first
            document.querySelectorAll('.comment-tooltip-popup.active').forEach(p => {{
                p.classList.remove('active');
            }});

            // If it wasn't open before, open it now
            if (!isOpen) {{
                popup.classList.add('active');
            }}
        }}

        // Close any active comment popup when clicking anywhere outside
        document.addEventListener('click', function(e) {{
            const activePopup = document.querySelector('.comment-tooltip-popup.active');
            if (activePopup && !activePopup.contains(e.target)) {{
                activePopup.classList.remove('active');
            }}
        }});
        </script>
    ''', height=480, scrolling=False)
def sleek_chart(status_count_df):
    color_map = {
        "Available for UAT": "#0f766e",
        "In Progress":       "#b45309",
        "Approved":          "#2563eb",
        "Done":              "#2563eb",
        "Blocked":           "#b42318",
        "To Do":             "#64748b",
    }
    df_sorted = status_count_df.sort_values('count', ascending=True)
    fig = px.bar(
        df_sorted,
        x='count',
        y='State',
        orientation='h',
        color='State',
        color_discrete_map=color_map,
        template="plotly_white",
    )
    chart_height = max(200, len(df_sorted) * 48 + 40)
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        showlegend=False,
        margin=dict(l=0, r=50, t=8, b=8),
        font=dict(family="Inter, sans-serif", size=13, color="#0f172a"),
        height=chart_height,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, visible=False)
    fig.update_yaxes(
        showgrid=False, zeroline=False,
        title_text="",
        tickfont=dict(size=13, color="#0f172a"),
    )
    fig.update_traces(
        texttemplate='%{x}',
        textposition='outside',
        cliponaxis=False,
        marker_line_width=0,
        textfont=dict(size=12, color="#0f172a"),
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APP
# ══════════════════════════════════════════════════════════════════════════════

local_css()
render_header()

# Load data (cached after first run)
df, comments_by_id, title_by_id = load_dashboard_data()

# ── Metrics ────────────────────────────────────────────────────────────────────
status_count = df['State'].value_counts().reset_index()
status_count.columns = ['State', 'count']
state_list = status_count.to_dict('records')

if 'selected_state' not in st.session_state:
    st.session_state['selected_state'] = None

st.markdown('### Overview')
render_kpi_cards(state_list, len(df), st.session_state['selected_state'])

# ── Filter Bar ─────────────────────────────────────────────────────────────────
filter_col, _ = st.columns([5, 1])
with filter_col:
    filter_options = ["All Board Columns"] + [row['State'] for row in state_list]
    selected_filter = st.radio(
        "Board Column",
        filter_options,
        horizontal=True,
        label_visibility="collapsed",
        key="state_filter_radio",
    )
    st.session_state['selected_state'] = (
        None if selected_filter == "All Board Columns" else selected_filter
    )

# ── Chart ──────────────────────────────────────────────────────────────────────
st.markdown('### Implementation Progress')
fig = sleek_chart(status_count)
st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

# ── Stories Table ──────────────────────────────────────────────────────────────
current_state = st.session_state['selected_state']
filtered_df = df if current_state is None else df[df['State'] == current_state]
state_label = "All Stories" if current_state is None else current_state

st.markdown('### User Stories')
st.markdown(
    f'<div style="color:#475569;font-size:14px;margin-bottom:12px;">'
    f'<span style="color:#0f172a;font-weight:700;">{len(filtered_df)}</span>'
    f'&nbsp;stories&nbsp;&mdash;&nbsp;{html.escape(state_label)}</div>',
    unsafe_allow_html=True,
)

table_display = filtered_df[['ID', 'Title', 'State', 'Comments', 'Attachments']].copy()
table_display.columns = ['ID', 'Title', 'State', 'Comments Count', 'Attachments Count']
render_stories_table(table_display, comments_by_id)

# ── Response Time Analysis (Pii vs SeaTec) ────────────────────────────────────
st.markdown('### Response Time Analysis (Pii vs SeaTec)')
st.markdown(
    '<div style="color:#475569;font-size:14px;margin-bottom:16px;">'
    'Tracking response turnarounds between <b style="color:#b45309;">Pii</b> and <b style="color:#2563eb;">SeaTec</b>. '
    'Showing individual turnaround splits, sorted strictly by <b>total cumulative turnaround time</b> (longest to shortest).</div>',
    unsafe_allow_html=True,
)

turnaround_df = analyze_comment_turnarounds(df, comments_by_id, title_by_id)

if not turnaround_df.empty:
    # 1. Calculate cumulative total turnaround duration per card to determine y-axis ordering
    card_totals = turnaround_df.groupby("Card Label")["Days"].sum().reset_index()
    card_totals_sorted = card_totals.sort_values("Days", ascending=False)

    # In Plotly horizontal bar charts, y-axis categoryarray lists categories from bottom to top.
    # Reversing categoryarray puts the card with the LONGEST CUMULATIVE DURATION at the TOP.
    longest_first_order = card_totals_sorted["Card Label"].tolist()[::-1]

    color_map = {"Pii": "#b45309", "SeaTec": "#2563eb"}
    
    # 2. Render stacked/split horizontal bar chart preserving individual turnaround splits
    fig_delays = px.bar(
        turnaround_df,
        x='Days',
        y='Card Label',
        orientation='h',
        color='Responding Party',
        color_discrete_map=color_map,
        template="plotly_white",
        title="Response Turnaround Duration (> 5 Days) — Sorted by Cumulative Total",
        hover_data=["Initial Author", "Respondent", "Response Date"]
    )

    chart_height = max(240, len(card_totals_sorted) * 45 + 50)
    fig_delays.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        barmode='stack',
        margin=dict(l=0, r=60, t=40, b=10),
        font=dict(family="Inter, sans-serif", size=13, color="#0f172a"),
        height=chart_height,
        legend=dict(
            title=dict(text="Responding Party", font=dict(color="#0f172a")),
            font=dict(color="#0f172a")
        )
    )

    # Enforce y-axis ordering based on cumulative total turnaround duration
    fig_delays.update_yaxes(
        categoryorder='array',
        categoryarray=longest_first_order,
        title_text="",
        tickfont=dict(size=12, color="#0f172a")
    )
    fig_delays.update_xaxes(
        showgrid=True,
        gridcolor="#e2e8f0",
        title_text="Turnaround Duration (Days)",
        title_font=dict(color="#0f172a"),
        tickfont=dict(color="#0f172a")
    )
    fig_delays.update_traces(
        texttemplate='%{x}d',
        textposition='inside',
        insidetextanchor='middle',
        textfont=dict(color="#ffffff", size=11, weight="bold")
    )

    st.plotly_chart(fig_delays, use_container_width=True, config={'displayModeBar': False})
else:
    st.markdown("""
        <div style="background:#ffffff; border:1px solid #e7ecf3; border-radius:16px; padding:32px; text-align:center; box-shadow:0 4px 16px rgba(15, 23, 42, 0.03);">
            <div style="font-size:16px; font-weight:700; color:#0f766e; margin-bottom:4px;">⚡ Excellent Communication Velocity</div>
            <div style="font-size:13px; color:#475569;">No response turnarounds between Pii and SeaTec exceeded 5 days.</div>
        </div>
    """, unsafe_allow_html=True)
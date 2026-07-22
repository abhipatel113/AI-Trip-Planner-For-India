"""
Yatra — AI Trip Planner for India (Streamlit version).
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime

import streamlit as st
from google import genai
from google.genai import types

# --- NEW IMPORT FOR RATE LIMIT HANDLING ---
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from pdf_export import build_pdf, pdf_filename
from share import build_payload, decode_share, encode_share

# ---------- Page config & theme ----------

st.set_page_config(
    page_title="Yatra — AI Trip Planner for India",
    page_icon="🧭",
    layout="centered",
    initial_sidebar_state="expanded",
)

ORANGE = "#EA6A20"

st.markdown(
    f"""
    <style>
      .stApp {{ background: #ffffff; }}
      h1, h2, h3 {{ color: #2b1d10; }}
      .yatra-title {{
        font-family: Georgia, "Times New Roman", serif;
        font-size: 2.6rem;
        font-weight: 700;
        color: #2b1d10;
        text-align: center;
        margin-bottom: 0.25rem;
      }}
      .yatra-title em {{ color: {ORANGE}; font-style: italic; }}
      .yatra-sub {{
        text-align: center;
        color: #6b6154;
        margin-bottom: 2rem;
      }}
      .day-card {{
        border: 1px solid #efe6db;
        border-radius: 16px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1rem;
        background: #fffdfa;
      }}
      .day-header {{
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        margin-bottom: 0.75rem;
      }}
      .day-title {{
        font-family: Georgia, serif;
        font-size: 1.4rem;
        color: {ORANGE};
        margin: 0;
      }}
      .day-cost {{ color: #6b6154; font-size: 0.85rem; }}
      .slot-label {{
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #6b6154;
      }}
      .food-heading {{
        border-top: 1px solid #efe6db;
        margin-top: 0.75rem;
        padding-top: 0.75rem;
      }}
      .stButton>button {{
        background: {ORANGE};
        color: white;
        border: 0;
        border-radius: 10px;
        padding: 0.6rem 1rem;
        font-weight: 600;
      }}
      .stButton>button:hover {{ background: #d25c17; color: white; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Session state ----------

if "history" not in st.session_state:
    st.session_state.history = []          
if "current_trip" not in st.session_state:
    st.session_state.current_trip = None   
if "current_meta" not in st.session_state:
    st.session_state.current_meta = None   
if "finalized_id" not in st.session_state:
    st.session_state.finalized_id = None
if "view_saved_id" not in st.session_state:
    st.session_state.view_saved_id = None
if "shared_payload" not in st.session_state:
    st.session_state.shared_payload = None
# --- NEW STATE FOR BUTTON ---
if "is_planning" not in st.session_state:
    st.session_state.is_planning = False

# ---------- Shared-link intake ----------

_qp = st.query_params
_trip_token = _qp.get("trip")
if _trip_token and st.session_state.shared_payload is None:
    decoded = decode_share(_trip_token)
    if decoded:
        st.session_state.shared_payload = decoded

# ---------- Options ----------

TRAVEL_STYLES = {
    "balanced": "Balanced",
    "relaxed": "Relaxed / slow",
    "adventure": "Adventure",
    "cultural": "Cultural & heritage",
    "nightlife": "Nightlife & cafes",
    "family": "Family friendly",
    "spiritual": "Spiritual",
    "luxury": "Luxury",
    "budget": "Backpacker / budget",
}

STYLE_GUIDE = {
    "balanced": "a balanced mix of sightseeing, culture, and relaxation",
    "relaxed": "a slow, unhurried pace with fewer stops and more downtime",
    "adventure": "outdoor and adventurous experiences (treks, water sports, active exploration)",
    "cultural": "history, heritage sites, museums, and local traditions",
    "nightlife": "vibrant evening spots, live music, cafes, and nightlife",
    "family": "family- and kid-friendly places that are safe and easy to navigate",
    "spiritual": "temples, ashrams, meditation, and reflective experiences",
    "luxury": "premium experiences, upscale venues, and refined dining",
    "budget": "affordable, backpacker-friendly picks that stretch the daily budget",
}

DIETS = {
    "no-preference": "No preference",
    "vegetarian": "Vegetarian",
    "vegan": "Vegan",
    "jain": "Jain",
    "halal": "Halal",
    "non-vegetarian": "Non-vegetarian",
    "gluten-free": "Gluten-free",
}

DIET_GUIDE = {
    "no-preference": "Any local cuisine is welcome.",
    "vegetarian": "Only vegetarian food. No meat, fish, or eggs in dishes.",
    "vegan": "Strictly vegan. No meat, fish, dairy, eggs, or honey.",
    "jain": "Jain-friendly food only. No onion, garlic, or root vegetables; strictly vegetarian.",
    "halal": "Halal-certified or reliably halal restaurants and dishes only.",
    "non-vegetarian": "Feel free to include meat, fish, and eggs; highlight local non-veg specialties.",
    "gluten-free": "Gluten-free options only. Avoid wheat-based breads and dishes.",
}

# ---------- Header ----------

st.markdown(
    '<div class="yatra-title">Plan your <em>India</em> trip</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="yatra-sub">A day-by-day AI itinerary in seconds.</div>',
    unsafe_allow_html=True,
)

# ---------- Sidebar ----------

with st.sidebar:
    st.markdown("### 📌 Saved trips")
    st.caption("Kept for this browser session.")
    if not st.session_state.history:
        st.write("_No saved trips yet. Finalize an itinerary to save it here._")
    else:
        for trip in reversed(st.session_state.history):
            with st.container(border=True):
                st.markdown(
                    f"**{trip['city']}** — {trip['days']}d · ₹{trip['budget']}/day"
                )
                st.caption(
                    datetime.fromtimestamp(trip["savedAt"]).strftime("%b %d, %Y %H:%M")
                )
                c1, c2 = st.columns(2)
                if c1.button("View", key=f"view-{trip['id']}"):
                    st.session_state.view_saved_id = trip["id"]
                    st.session_state.current_trip = None
                    st.rerun()
                if c2.button("Delete", key=f"del-{trip['id']}"):
                    st.session_state.history = [
                        t for t in st.session_state.history if t["id"] != trip["id"]
                    ]
                    if st.session_state.view_saved_id == trip["id"]:
                        st.session_state.view_saved_id = None
                    st.rerun()

# ---------- Inputs ----------

with st.form("trip_form"):
    city = st.text_input("City", placeholder="e.g. Jaipur, Goa, Varanasi")
    col1, col2 = st.columns(2)
    with col1:
        days = st.number_input("Days", min_value=1, max_value=14, value=3, step=1)
    with col2:
        budget = st.number_input(
            "Budget / day (₹)", min_value=100, max_value=500_000, value=2500, step=100
        )
    col3, col4 = st.columns(2)
    with col3:
        travel_style = st.selectbox(
            "Travel style",
            options=list(TRAVEL_STYLES.keys()),
            format_func=lambda k: TRAVEL_STYLES[k],
            index=0,
        )
    with col4:
        diet = st.selectbox(
            "Dietary preference",
            options=list(DIETS.keys()),
            format_func=lambda k: DIETS[k],
            index=0,
        )
    # Button is now connected to session state to prevent double-clicking
    submitted = st.form_submit_button("Plan my trip →", use_container_width=True, disabled=st.session_state.is_planning)

# ---------- AI call ----------

def get_api_key() -> str | None:
    try:
        key = st.secrets["GEMINI_API_KEY"]  
    except Exception:
        key = os.environ.get("GEMINI_API_KEY")
    
    # ADD THIS PRINT STATEMENT
    if key:
        print(f"\n[DEBUG] Currently using API Key starting with: {key[:8]}...")
    else:
        print("\n[DEBUG] WARNING: NO API KEY DETECTED!")
        
    return key

def build_prompt(city: str, days: int, budget: int, style: str, diet_key: str) -> str:
    return f"""You are an expert India travel planner. Create a realistic {days}-day itinerary for {city}, India, on a per-day budget of INR {budget}.

Traveler preferences:
- Travel style: {style} — favor {STYLE_GUIDE[style]}.
- Dietary preference: {diet_key} — {DIET_GUIDE[diet_key]}

Respond ONLY with a JSON object (no markdown fences, no prose) matching this exact TypeScript type:
{{
  "summary": string,
  "days": Array<{{
    "morning": string,
    "afternoon": string,
    "evening": string,
    "food": string[],
    "estimatedCost": number
  }}>
}}

Rules:
- Use real, well-known places in {city} that match the travel style above.
- Keep each activity to 1-2 sentences.
- Return exactly {days} day objects.
- "food" is 2-3 concrete local dishes or restaurants that strictly respect the dietary preference above.
- "estimatedCost" is an integer INR total for that day, close to {budget}.
- "summary" is a single sentence describing the overall trip and reflecting the traveler's style.
"""

def parse_json(text: str) -> dict:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)

# --- EXPONENTIAL BACKOFF LOGIC ADDED HERE ---
@retry(
    stop=stop_after_attempt(5), 
    wait=wait_exponential(multiplier=1.5, min=2, max=15), 
    retry=retry_if_exception_type(Exception),
    reraise=True
)
def plan_trip(city: str, days: int, budget: int, style: str, diet_key: str) -> dict:
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=build_prompt(city, days, budget, style, diet_key),
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return parse_json(response.text or "")

# ---------- Error mapping ----------

def friendly_error(err: Exception) -> tuple[str, str, bool]:
    msg = str(err)
    low = msg.lower()
    if "429" in msg or "rate" in low and "limit" in low:
        return (
            "⏳ The planner is still busy",
            "Google's Free Tier is heavily overloaded right now. We tried multiple times in the background but it's still rejecting requests. Please wait 1-2 minutes and try again.",
            True,
        )
    if "402" in msg or any(k in low for k in ("credit", "quota", "billing")):
        return (
            "💳 AI credits ran out",
            "The Gemini API daily quota is exhausted. Check your Google AI Studio billing.",
            False,
        )
    if any(k in low for k in ("timeout", "timed out", "network", "connection", "fetch failed")):
        return (
            "📡 Couldn't reach the planner",
            "There was a network hiccup. Check your connection and try again.",
            True,
        )
    if "api key" in low or "gemini_api_key" in low:
        return (
            "🔑 API key not configured",
            msg,
            False,
        )
    if isinstance(err, (json.JSONDecodeError, ValueError, KeyError)):
        return (
            "⚠️ We couldn't read the response",
            "The AI returned something unexpected. Retrying usually fixes it.",
            True,
        )
    return ("⚠️ Something went wrong", msg or "Please try again in a moment.", True)

# ---------- Render helpers ----------

def render_day_readonly(i: int, d: dict) -> None:
    cost = d.get("estimatedCost", 0)
    try:
        cost_str = f"₹{int(cost):,}"
    except (TypeError, ValueError):
        cost_str = f"₹{cost}"

    st.markdown('<div class="day-card">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="day-header"><h3 class="day-title">Day {i}</h3>'
        f'<span class="day-cost">≈ {cost_str}</span></div>',
        unsafe_allow_html=True,
    )
    for label, key in (("Morning", "morning"), ("Afternoon", "afternoon"), ("Evening", "evening")):
        st.markdown(
            f'<div style="margin-bottom:0.6rem"><span class="slot-label">{label}</span><br>{d.get(key, "")}</div>',
            unsafe_allow_html=True,
        )
    food = d.get("food") or []
    if food:
        st.markdown('<div class="food-heading">', unsafe_allow_html=True)
        st.markdown('<span class="slot-label">Food to try</span>', unsafe_allow_html=True)
        for item in food:
            st.markdown(f'<div style="margin-top:0.25rem">• {item}</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

def render_day_editable(i: int, d: dict, locked: bool) -> dict:
    cost = d.get("estimatedCost", 0)
    try:
        cost_str = f"₹{int(cost):,}"
    except (TypeError, ValueError):
        cost_str = f"₹{cost}"

    with st.container(border=True):
        header_l, header_r = st.columns([3, 1])
        header_l.markdown(
            f"<h3 class='day-title'>Day {i}</h3>", unsafe_allow_html=True
        )
        header_r.markdown(
            f"<div style='text-align:right' class='day-cost'>≈ {cost_str}</div>",
            unsafe_allow_html=True,
        )

        if locked:
            for label, key in (("Morning", "morning"), ("Afternoon", "afternoon"), ("Evening", "evening")):
                st.markdown(
                    f'<div style="margin-bottom:0.6rem"><span class="slot-label">{label}</span><br>{d.get(key, "")}</div>',
                    unsafe_allow_html=True,
                )
            food = d.get("food") or []
            if food:
                st.markdown('<span class="slot-label">Food to try</span>', unsafe_allow_html=True)
                for item in food:
                    st.markdown(f"- {item}")
            return d

        morning = st.text_area("Morning", value=d.get("morning", ""), key=f"m-{i}", height=80)
        afternoon = st.text_area("Afternoon", value=d.get("afternoon", ""), key=f"a-{i}", height=80)
        evening = st.text_area("Evening", value=d.get("evening", ""), key=f"e-{i}", height=80)
        food_text = st.text_area(
            "Food to try (one per line)",
            value="\n".join(d.get("food", []) or []),
            key=f"f-{i}",
            height=90,
        )
        return {
            **d,
            "morning": morning.strip(),
            "afternoon": afternoon.strip(),
            "evening": evening.strip(),
            "food": [line.strip() for line in food_text.splitlines() if line.strip()],
        }

def render_itinerary_editor() -> None:
    trip = st.session_state.current_trip
    meta = st.session_state.current_meta
    if not trip or not meta:
        return

    locked = st.session_state.finalized_id is not None

    st.markdown(
        f"### <em style='color:{ORANGE}'>{meta['city']}</em>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"{meta['days']} day{'s' if meta['days'] > 1 else ''} · ₹{meta['budget']}/day · "
        f"{TRAVEL_STYLES[meta['style']]} · {DIETS[meta['diet']]}"
    )
    if trip.get("summary"):
        st.write(trip["summary"])

    if locked:
        st.success("🔒 Finalized and saved to your history. Unlock to keep editing.")
        c1, c2 = st.columns(2)
        if c1.button("Unlock to edit"):
            st.session_state.finalized_id = None
            st.rerun()
        pdf_bytes = build_pdf(
            trip,
            {
                "city": meta["city"],
                "days": meta["days"],
                "budget": meta["budget"],
                "style": TRAVEL_STYLES.get(meta["style"], meta["style"]),
                "diet": DIETS.get(meta["diet"], meta["diet"]),
            },
        )
        c2.download_button(
            "⬇️ Download PDF",
            data=pdf_bytes,
            file_name=pdf_filename(meta["city"], meta["days"]),
            mime="application/pdf",
            use_container_width=True,
        )
        _render_share_section(
            build_payload(
                trip,
                meta["city"],
                meta["days"],
                meta["budget"],
                TRAVEL_STYLES.get(meta["style"], meta["style"]),
                DIETS.get(meta["diet"], meta["diet"]),
            )
        )
    else:
        st.info("Edit any day below, then finalize to save it to your history.")

    updated_days = []
    for i, day in enumerate(trip.get("days", []), start=1):
        updated_days.append(render_day_editable(i, day, locked))

    if not locked:
        st.session_state.current_trip = {**trip, "days": updated_days}

        cA, cB = st.columns(2)
        if cA.button("💾 Finalize & save", use_container_width=True):
            saved = {
                "id": uuid.uuid4().hex,
                "city": meta["city"],
                "days": meta["days"],
                "budget": meta["budget"],
                "style": meta["style"],
                "diet": meta["diet"],
                "savedAt": time.time(),
                "itinerary": st.session_state.current_trip,
            }
            st.session_state.history.append(saved)
            st.session_state.finalized_id = saved["id"]
            st.rerun()
        if cB.button("Start over", use_container_width=True):
            st.session_state.current_trip = None
            st.session_state.current_meta = None
            st.session_state.finalized_id = None
            st.rerun()

def render_saved_view() -> None:
    sid = st.session_state.view_saved_id
    trip = next((t for t in st.session_state.history if t["id"] == sid), None)
    if not trip:
        st.warning("Saved trip not found.")
        st.session_state.view_saved_id = None
        return

    st.markdown(
        f"### <em style='color:{ORANGE}'>{trip['city']}</em> — saved",
        unsafe_allow_html=True,
    )
    st.caption(
        f"{trip['days']} day{'s' if trip['days'] > 1 else ''} · ₹{trip['budget']}/day · "
        f"{TRAVEL_STYLES.get(trip.get('style','balanced'),'')} · {DIETS.get(trip.get('diet','no-preference'),'')} · "
        f"saved {datetime.fromtimestamp(trip['savedAt']).strftime('%b %d, %Y %H:%M')}"
    )
    summary = trip["itinerary"].get("summary")
    if summary:
        st.write(summary)
    for i, d in enumerate(trip["itinerary"].get("days", []), start=1):
        render_day_readonly(i, d)

    st.download_button(
        "⬇️ Download JSON",
        data=json.dumps(trip, indent=2, ensure_ascii=False),
        file_name=f"yatra-{trip['city'].lower().replace(' ', '-')}.json",
        mime="application/json",
    )
    pdf_bytes = build_pdf(
        trip["itinerary"],
        {
            "city": trip["city"],
            "days": trip["days"],
            "budget": trip["budget"],
            "style": TRAVEL_STYLES.get(trip.get("style", "balanced"), ""),
            "diet": DIETS.get(trip.get("diet", "no-preference"), ""),
        },
    )
    st.download_button(
        "⬇️ Download PDF",
        data=pdf_bytes,
        file_name=pdf_filename(trip["city"], trip["days"]),
        mime="application/pdf",
    )
    _render_share_section(
        build_payload(
            trip["itinerary"],
            trip["city"],
            trip["days"],
            trip["budget"],
            TRAVEL_STYLES.get(trip.get("style", "balanced"), ""),
            DIETS.get(trip.get("diet", "no-preference"), ""),
        )
    )
    if st.button("← Back"):
        st.session_state.view_saved_id = None
        st.rerun()

def _get_base_url() -> str:
    try:
        headers = st.context.headers 
        host = headers.get("Host") or headers.get("X-Forwarded-Host")
        proto = headers.get("X-Forwarded-Proto") or "https"
        if host:
            return f"{proto}://{host}"
    except Exception as e: 
                # ADD THESE PRINT STATEMENTS TO UNMASK THE RAW ERROR
                print("\n" + "="*50)
                print(f"RAW GOOGLE API ERROR: {e}")
                print("="*50 + "\n")

                title, desc, retryable = friendly_error(e)
                st.error(f"**{title}**\n\n{desc}")
                if retryable:
                    st.caption("Tip: wait a moment and press **Plan my trip** again.")
        
    return ""

def _render_share_section(payload: dict) -> None:
    token = encode_share(payload)
    base = _get_base_url()
    link = f"{base}/?trip={token}" if base else f"?trip={token}"
    st.markdown("#### 🔗 Share this itinerary")
    st.caption(
        "Anyone with this link can view the itinerary — no account needed. "
        "It contains the full trip encoded in the URL."
        + ("" if base else " (Open the app and append the query below to its URL.)")
    )
    st.code(link, language="text")

def render_shared_view() -> None:
    payload = st.session_state.shared_payload
    if not payload:
        return
    itin = payload["itinerary"]
    st.info("👀 You're viewing a shared itinerary.")
    st.markdown(
        f"### <em style='color:{ORANGE}'>{payload['city']}</em> — shared",
        unsafe_allow_html=True,
    )
    style_label = payload.get("travelStyle") or ""
    diet_label = payload.get("diet") or ""
    st.caption(
        f"{payload['days']} day{'s' if payload['days'] > 1 else ''} · ₹{payload['budget']}/day"
        + (f" · {style_label}" if style_label else "")
        + (f" · {diet_label}" if diet_label else "")
    )
    if itin.get("summary"):
        st.write(itin["summary"])
    for i, d in enumerate(itin.get("days", []), start=1):
        render_day_readonly(i, d)

    pdf_bytes = build_pdf(
        itin,
        {
            "city": payload["city"],
            "days": payload["days"],
            "budget": payload["budget"],
            "style": style_label,
            "diet": diet_label,
        },
    )
    st.download_button(
        "⬇️ Download PDF",
        data=pdf_bytes,
        file_name=pdf_filename(payload["city"], payload["days"]),
        mime="application/pdf",
    )
    if st.button("Plan your own trip"):
        st.session_state.shared_payload = None
        try:
            st.query_params.clear()
        except Exception:
            pass
        st.rerun()

# ---------- Main flow ----------

if submitted:
    if not city.strip():
        st.warning("Please enter a city to continue.")
    else:
        st.session_state.view_saved_id = None
        st.session_state.is_planning = True # Disable the button
        
        with st.spinner("Crafting your itinerary… (this might take up to 30 seconds if the API is busy)"):
            try:
                data = plan_trip(
                    city.strip(), int(days), int(budget), travel_style, diet
                )
                st.session_state.current_trip = data
                st.session_state.current_meta = {
                    "city": city.strip(),
                    "days": int(days),
                    "budget": int(budget),
                    "style": travel_style,
                    "diet": diet,
                }
                st.session_state.finalized_id = None
            except Exception as e: 
                title, desc, retryable = friendly_error(e)
                st.error(f"**{title}**\n\n{desc}")
                if retryable:
                    st.caption("Tip: wait a moment and press **Plan my trip** again.")
            finally:
                st.session_state.is_planning = False 

if st.session_state.shared_payload:
    render_shared_view()
elif st.session_state.view_saved_id:
    render_saved_view()
elif st.session_state.current_trip:
    render_itinerary_editor()
else:
    st.caption("Enter your trip details above and press **Plan my trip**.")
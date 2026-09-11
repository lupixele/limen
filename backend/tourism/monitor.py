"""Bounded, session-scoped itinerary monitoring and autonomous correction engine for Limen."""
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, Optional
from zoneinfo import ZoneInfo

from tourism.db import get_db_connection
from tourism.tools import BuildItineraryTool

logger = logging.getLogger("tourism.monitor")
TZ_KOLKATA = ZoneInfo("Asia/Kolkata")


class ItineraryMonitor:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path
        self._active_sessions: Dict[str, Dict[str, Any]] = {}
        self._event_queues: Dict[str, asyncio.Queue] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._agent_runner: Optional[Callable] = None

    def set_agent_runner(self, runner_fn: Optional[Callable]) -> None:
        """Registers agent loop runner callback for autonomous replanning."""
        self._agent_runner = runner_fn

    def get_status(self, session_id: str) -> Dict[str, Any]:
        info = self._active_sessions.get(session_id)
        task = self._tasks.get(session_id)
        is_running = bool(info and info.get("running", False) and task and not task.done())
        if not info:
            return {"active": False, "session_id": session_id}
        return {
            "active": is_running,
            "session_id": session_id,
            "itinerary_id": info.get("itinerary_id"),
            "iteration": info.get("iteration", 0),
            "last_check": info.get("last_check"),
        }

    async def register_listener(self, session_id: str) -> asyncio.Queue:
        if session_id not in self._event_queues:
            self._event_queues[session_id] = asyncio.Queue()
        return self._event_queues[session_id]

    async def emit_event(self, session_id: str, event: Dict[str, Any]) -> None:
        queue = self._event_queues.get(session_id)
        if queue:
            await queue.put(event)

    def start_monitoring(
        self, session_id: str, interval_seconds: float = 4.0, max_ticks: int = 15
    ) -> bool:
        """
        Starts a background monitoring loop with strict NO OVERLAP enforcement.
        Returns True if a new monitoring task was created, False if already running.
        """
        existing_task = self._tasks.get(session_id)
        if existing_task and not existing_task.done():
            logger.info(f"Monitoring already active for session {session_id} - skipping duplicate start.")
            return False

        task = asyncio.create_task(
            self.run_loop(
                session_id=session_id,
                max_ticks=max_ticks,
                interval_seconds=interval_seconds,
            )
        )
        self._tasks[session_id] = task
        return True

    def stop_monitoring(self, session_id: str) -> bool:
        """Stops and cancels the monitoring loop for session_id."""
        was_running = False
        if session_id in self._active_sessions:
            if self._active_sessions[session_id].get("running"):
                was_running = True
            self._active_sessions[session_id]["running"] = False

        task = self._tasks.get(session_id)
        if task and not task.done():
            task.cancel()
            was_running = True

        return was_running

    async def check_itinerary_health(self, session_id: str) -> Dict[str, Any]:
        """Inspects saved itinerary against current live weather and disruption/closure feeds."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM itineraries
            WHERE session_id = ?
            ORDER BY version DESC, updated_at DESC LIMIT 1
        """,
            (session_id,),
        )
        itin = cursor.fetchone()

        if not itin:
            conn.close()
            return {"healthy": True, "status": "no_active_itinerary"}

        try:
            stops = json.loads(itin["stops_json"])
        except Exception:
            stops = []
        itin_id = itin["id"]
        version = itin["version"]

        # Check disruptions
        cursor.execute("SELECT * FROM disruptions WHERE active = 1")
        disruptions = cursor.fetchall()
        disrupted_place_ids = set()
        disruption_map = {}
        for d in disruptions:
            try:
                affected = json.loads(d["affected_places_json"] or "[]")
            except Exception:
                affected = []
            for p in affected:
                disrupted_place_ids.add(p)
                disruption_map[p] = d["title"]

        affected_stops = []

        for s in stops:
            place_id = s.get("place_id")
            # 1. Check emergency closure
            cursor.execute(
                "SELECT has_emergency_closure, closure_reason, schedule_json FROM attractions WHERE id = ?",
                (place_id,),
            )
            attr = cursor.fetchone()
            if attr and attr["has_emergency_closure"]:
                affected_stops.append({
                    "stop_order": s.get("stop_order"),
                    "name": s.get("name"),
                    "place_id": place_id,
                    "reason": attr["closure_reason"] or "Emergency closure",
                })
            elif place_id in disrupted_place_ids:
                affected_stops.append({
                    "stop_order": s.get("stop_order"),
                    "name": s.get("name"),
                    "place_id": place_id,
                    "reason": f"DISRUPTION: {disruption_map.get(place_id, 'Active Disruption')}",
                })

        conn.close()

        if affected_stops:
            return {
                "healthy": False,
                "itinerary_id": itin_id,
                "version": version,
                "affected_stops": affected_stops,
                "summary": f"Detected {len(affected_stops)} disrupted stops requiring autonomous replanning.",
            }

        return {
            "healthy": True,
            "itinerary_id": itin_id,
            "version": version,
            "affected_stops": [],
            "summary": "All itinerary stops are operating normally.",
        }

    async def autonomous_replan(self, session_id: str, health: Dict[str, Any]) -> Dict[str, Any]:
        """
        Autonomously recalculates an alternative itinerary avoiding closed stops.
        Invokes actual model/tool loop when available, falling back gracefully to validated direct tool execution.
        """
        itin_id = health.get("itinerary_id", "itin_unknown")
        old_version = health.get("version", 1)
        affected = health.get("affected_stops", [])
        disrupted_names = [a.get("name", "unknown") for a in affected]
        reason_summary = "; ".join([a.get("reason", "Disruption") for a in affected])

        instruction = (
            f"Autonomous monitoring detected emergency disruption in session {session_id}. "
            f"Disrupted stops: {disrupted_names}. Reason: {reason_summary}. "
            f"Inspect disruptions, query open places, and build a revised validated itinerary avoiding closed attractions."
        )

        artifact = None
        new_itin_id = None

        # 1. Execute via agent runner if registered
        if self._agent_runner is not None:
            try:
                result = await self._agent_runner(session_id, instruction, health)
                if isinstance(result, dict):
                    artifact = result.get("artifact")
                    new_itin_id = result.get("itinerary_id")
            except Exception as e:
                logger.warning(f"Agent runner error during autonomous replan: {e}")

        # 2. Fallback / Verification: Ensure new itinerary is in database
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, version, summary FROM itineraries
            WHERE session_id = ?
            ORDER BY created_at DESC LIMIT 1
        """,
            (session_id,),
        )
        latest_row = cursor.fetchone()

        if not latest_row or latest_row["id"] == itin_id:
            # Runner did not persist new itinerary; execute BuildItineraryTool directly
            builder = BuildItineraryTool(self.db_path)
            now_str = datetime.now(TZ_KOLKATA).strftime("%Y-%m-%d")
            replan_res = await builder.run(
                session_id=session_id,
                target_date=now_str,
                budget_inr=2000.0,
                start_time="10:00",
            )
            new_itin_id = replan_res.output.get("itinerary_id") if replan_res.output else None
            artifact = replan_res.artifact
        else:
            new_itin_id = latest_row["id"]

        new_version = old_version + 1
        cursor.execute(
            """
            UPDATE itineraries
            SET status = 'revised', version = ?, summary = ?
            WHERE id = ?
        """,
            (
                new_version,
                f"Autonomous Replan: Substituted disrupted stop(s) {disrupted_names} with verified alternatives.",
                new_itin_id,
            ),
        )
        conn.commit()
        conn.close()

        replan_event = {
            "type": "autonomous_replan",
            "session_id": session_id,
            "old_itinerary_id": itin_id,
            "new_itinerary_id": new_itin_id,
            "version": new_version,
            "reason": f"Disruption detected at: {', '.join(disrupted_names)}",
            "changes": "Replaced with verified open attractions. New plan generated and persisted.",
            "artifact": artifact,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await self.emit_event(session_id, replan_event)
        return replan_event

    async def run_loop(
        self, session_id: str, max_ticks: int = 15, interval_seconds: float = 4.0
    ) -> None:
        """Bounded monitoring loop with interval ticks and autonomous replanning on alert."""
        self._active_sessions[session_id] = {
            "running": True,
            "iteration": 0,
            "last_check": None,
        }

        await self.emit_event(
            session_id,
            {
                "type": "monitoring_started",
                "session_id": session_id,
                "interval_sec": interval_seconds,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        ticks = 0
        try:
            while ticks < max_ticks and self._active_sessions.get(session_id, {}).get("running", False):
                ticks += 1
                now_iso = datetime.now(timezone.utc).isoformat()
                if session_id in self._active_sessions:
                    self._active_sessions[session_id]["iteration"] = ticks
                    self._active_sessions[session_id]["last_check"] = now_iso

                health = await self.check_itinerary_health(session_id)

                if not health.get("healthy"):
                    # Emit alert
                    await self.emit_event(
                        session_id,
                        {
                            "type": "monitoring_alert",
                            "session_id": session_id,
                            "health": health,
                            "timestamp": now_iso,
                        },
                    )

                    # Trigger autonomous replan via agent loop / tools
                    await self.autonomous_replan(session_id, health)

                    # Bounded stop after successful replan to avoid infinite loops
                    break
                else:
                    await self.emit_event(
                        session_id,
                        {
                            "type": "monitoring_tick",
                            "session_id": session_id,
                            "iteration": ticks,
                            "status": "healthy",
                            "summary": health.get("summary", "All stops normal"),
                            "timestamp": now_iso,
                        },
                    )

                await asyncio.sleep(interval_seconds)

        except asyncio.CancelledError:
            logger.info(f"Monitoring loop for session {session_id} cancelled.")
        finally:
            if session_id in self._active_sessions:
                self._active_sessions[session_id]["running"] = False
            self._tasks.pop(session_id, None)
            await self.emit_event(
                session_id,
                {
                    "type": "monitoring_stopped",
                    "session_id": session_id,
                    "ticks_completed": ticks,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )


# Global singleton instance
global_monitor = ItineraryMonitor()

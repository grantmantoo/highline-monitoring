"""
Highline Tech -- shared device core
===================================
Single source of truth for the pieces every device monitor shares:

  * ha.py        -- HAClient (real REST + WebSocket transport) + SimulatedHA
  * notifier.py  -- the unified alert -> notification path (one place decides how
                    an alert becomes an elder-care notification)
  * house_config -- loads the house config that run.py uses to start monitors

Device modules import these as top-level modules after putting this directory on
sys.path (a two-line bootstrap at the top of each module), so the same code runs
whether a device folder is exercised on its own or wired together by devices/run.py.
"""

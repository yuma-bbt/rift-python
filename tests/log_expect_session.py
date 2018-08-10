import datetime
import tools.log_record

class LogExpectSession:

    def __init__(self, log_file_name):
        self._log_file_name = log_file_name
        self._log_file = None
        self._expect_log_file = open('log_expect.log', 'w')
        self._line_nr = 0
        self._last_timestamp = None

    def open(self):
        self._log_file = open(self._log_file_name, "r")
        self._line_nr = 0
        self._expect_log_file.write("Open LogExpectSession\n\n")

    def close(self):
        self._log_file.close()
        self._expect_log_file.write("Close LogExpectSession\n\n")

    def write_record_to_expect_log_file(self, record):
        msg = ("Observerd FSM transition:\n"
               "  log-line-nr = {}\n"
               "  sequence-nr = {}\n"
               "  from-state = {}\n"
               "  event = {}\n"
               "  actions-and-pushed-events = {}\n"
               "  to-state = {}\n"
               "  implicit = {}\n"
               "\n").format(self._line_nr,
                            record.sequence_nr,
                            record.from_state,
                            record.event,
                            record.actions_and_pushed_events,
                            record.to_state,
                            record.implicit)
        self._expect_log_file.write(msg)

    def get_next_fsm_record_for_target(self, target_id):
        while True:
            line = self._log_file.readline()
            if not line:
                return None
            self._line_nr += 1
            record = tools.log_record.LogRecord(self._line_nr, line)
            if record.type == "transition" and record.target_id == target_id:
                self.write_record_to_expect_log_file(record)
                return record

    def fsm_expect(self, target_id, from_state, event, to_state, skip_events=None, max_delay=None):
        msg = ("Searching for FSM transition:\n"
               "  target-id = {}\n"
               "  from-state = {}\n"
               "  event = {}\n"
               "  to-state = {}\n"
               "  skip-events = {}\n"
               "\n").format(target_id,
                            from_state,
                            event,
                            to_state,
                            skip_events)
        self._expect_log_file.write(msg)
        while True:
            record = self.get_next_fsm_record_for_target(target_id)
            if not record:
                msg = "Did not find FSM transition for target-id {}".format(target_id)
                self._expect_log_file.write(msg)
                assert False, msg
            if skip_events and record.event in skip_events:
                continue
            if record.from_state != from_state:
                msg = ("FSM transition has from-state {} instead of expected from-state {}"
                       .format(record.from_state, from_state))
                self._expect_log_file.write(msg)
                assert False, msg
            if record.event != event:
                msg = ("FSM transition has event {} instead of expected event {}"
                       .format(record.event, event))
                self._expect_log_file.write(msg)
                assert False, msg
            if record.to_state != to_state:
                msg = ("FSM transition has to-state {} instead of expected to-state {}"
                       .format(record.to_state, to_state))
                self._expect_log_file.write(msg)
                assert False, msg
            timestamp = datetime.datetime.strptime(record.timestamp, "%Y-%m-%d %H:%M:%S,%f")
            if max_delay:
                if not self._last_timestamp:
                    msg = "Maxdelay specified in fsm_expect, but no previous event"
                    self._expect_log_file.write(msg)
                    assert False, msg
                delta = timestamp - self._last_timestamp
                delta_seconds = delta.total_seconds() + delta.microseconds / 1000000.0
                if delta_seconds > max_delay:
                    msg = ("Actual delay {} exceeds maximum delay {}"
                           .format(delta_seconds, max_delay))
                    self._expect_log_file.write(msg)
                    assert False, msg
            self._last_timestamp = timestamp
            self._expect_log_file.write("Found expected log transition\n\n")
            return record

    def check_lie_fsm_3way(self, system_id, interface):
        target_id = system_id + "-" + interface
        self.open()
        self.fsm_expect(
            target_id=target_id,
            from_state="ONE_WAY",
            event="LIE_RECEIVED",
            to_state="None",
            skip_events=["TIMER_TICK", "SEND_LIE"])
        self.fsm_expect(
            target_id=target_id,
            from_state="ONE_WAY",
            event="NEW_NEIGHBOR",
            to_state="TWO_WAY",
            skip_events=["TIMER_TICK", "SEND_LIE"])
        self.fsm_expect(
            target_id=target_id,
            from_state="TWO_WAY",
            event="SEND_LIE",
            to_state="None",
            skip_events=["TIMER_TICK"],
            max_delay=0.1)      # Our LIE should be triggered
        # Note: if the remote side receives the LIE packet that we just sent out above, we should
        # receive a LIE "quickly" which the SEND_LIE event on the remote node is triggerd by the
        # RECEIVE_LIE event. I had a max_delay of 0.1 in the expect below to check for that.
        # However, in some environments it takes some time for the initial IGMP joins to be
        # processed. The remote node may not receive the LIE which we sent out above, in which case
        # one ore more timer ticks are needed. I had to remove the max_delay.
        self.fsm_expect(
            target_id=target_id,
            from_state="TWO_WAY",
            event="LIE_RECEIVED",
            to_state="None",
            skip_events=["TIMER_TICK", "SEND_LIE"])
        # For the same reason as described above, the remote node may send us multiple LIE messages
        # before it sees the first LIE message sent from this node. Thus, we need to ignore
        # additional LIE_RECEIVED events while looking for the expected VALID_REFLECTION event.
        self.fsm_expect(
            target_id=target_id,
            from_state="TWO_WAY",
            event="VALID_REFLECTION",
            to_state="THREE_WAY",
            skip_events=["TIMER_TICK", "SEND_LIE", "LIE_RECEIVED"])
        self.close()

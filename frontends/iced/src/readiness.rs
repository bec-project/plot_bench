//! One operation in flight and one replaceable candidate, without GPU dependencies.

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct Identity {
    pub epoch: u64,
    pub generation: u64,
    pub seq: u64,
}

pub struct Readiness<T> {
    newest: Option<Identity>,
    active: Option<Identity>,
    candidate: Option<(Identity, T)>,
    closed: bool,
}

impl<T> Default for Readiness<T> {
    fn default() -> Self {
        Self {
            newest: None,
            active: None,
            candidate: None,
            closed: false,
        }
    }
}

impl<T> Readiness<T> {
    pub fn offer(&mut self, identity: Identity, value: T) {
        if self.closed || self.newest.is_some_and(|newest| identity <= newest) {
            return;
        }
        self.newest = Some(identity);
        self.candidate = Some((identity, value));
    }

    pub fn start_next(&mut self) -> Option<(Identity, T)> {
        if self.closed || self.active.is_some() {
            return None;
        }
        let next = self.candidate.take()?;
        self.active = Some(next.0);
        Some(next)
    }

    pub fn has_candidate(&self) -> bool {
        !self.closed && self.candidate.is_some()
    }

    /// Completion releases the slot even if a newer generation invalidated it.
    pub fn complete(&mut self, identity: Identity) -> bool {
        if self.active != Some(identity) {
            return false;
        }
        self.active = None;
        !self.closed
            && self.newest.is_some_and(|newest| {
                (newest.epoch, newest.generation) == (identity.epoch, identity.generation)
            })
    }

    pub fn close(&mut self) {
        self.closed = true;
        self.candidate = None;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn id(generation: u64, seq: u64) -> Identity {
        Identity {
            epoch: 0,
            generation,
            seq,
        }
    }

    #[test]
    fn pending_upload_keeps_only_latest_candidate_without_starving_active_frame() {
        let mut queue = Readiness::default();
        queue.offer(id(1, 1), "first");
        assert_eq!(queue.start_next(), Some((id(1, 1), "first")));
        for seq in 2..1000 {
            queue.offer(id(1, seq), "latest");
        }
        assert_eq!(queue.start_next(), None);
        assert!(queue.complete(id(1, 1)));
        assert_eq!(queue.start_next(), Some((id(1, 999), "latest")));
        assert!(queue.complete(id(1, 999)));
        assert_eq!(queue.start_next(), None);
    }

    #[test]
    fn new_generation_rejects_old_upload_and_late_old_packets() {
        let mut queue = Readiness::default();
        queue.offer(id(1, 100), "old image");
        queue.start_next();
        queue.offer(id(2, 0), "new waveform");
        queue.offer(id(1, 999), "late stale packet");
        assert!(!queue.complete(id(1, 100)));
        assert_eq!(queue.start_next(), Some((id(2, 0), "new waveform")));
        assert!(queue.complete(id(2, 0)));
    }

    #[test]
    fn mismatched_completion_cannot_release_another_operation() {
        let mut queue = Readiness::default();
        queue.offer(id(3, 0), 1);
        queue.start_next();
        queue.offer(id(3, 1), 2);
        assert!(!queue.complete(id(2, 0)));
        assert_eq!(queue.start_next(), None);
        assert!(queue.complete(id(3, 0)));
        assert_eq!(queue.start_next(), Some((id(3, 1), 2)));
    }

    #[test]
    fn close_drops_candidate_and_rejects_late_completion_and_new_work() {
        let mut queue = Readiness::default();
        queue.offer(id(1, 0), 1);
        queue.start_next();
        queue.offer(id(1, 1), 2);
        queue.close();
        queue.offer(id(1, 2), 3);
        assert!(!queue.complete(id(1, 0)));
        assert_eq!(queue.start_next(), None);
    }

    #[test]
    fn replay_sequence_duplicates_and_reordering_are_ignored() {
        let mut queue = Readiness::default();
        queue.offer(id(1, 8), "selected");
        queue.offer(id(1, 8), "duplicate");
        queue.offer(id(1, 7), "late");
        assert_eq!(queue.start_next(), Some((id(1, 8), "selected")));
    }

    #[test]
    fn reconnect_accepts_reset_sequences_and_rejects_previous_connection_completion() {
        let mut queue = Readiness::default();
        queue.offer(id(9, 100), "previous source");
        queue.start_next();
        let restarted = Identity {
            epoch: 1,
            generation: 0,
            seq: 0,
        };
        queue.offer(restarted, "restarted source");
        assert!(!queue.complete(id(9, 100)));
        assert_eq!(queue.start_next(), Some((restarted, "restarted source")));
        assert!(queue.complete(restarted));
    }
}

pub fn reset_incremental_builds(ready: bool) -> u32 {
    if ready {
        1
    } else {
        "reset"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ready_state_is_numeric() {
        assert_eq!(reset_incremental_builds(true), 1);
    }
}

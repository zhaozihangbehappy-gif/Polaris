pub fn double(value: i32) -> i32 {
    value * 2
}

#[cfg(test)]
mod tests {
    use super::double;

    #[test]
    fn doubles_an_integer() {
        assert_eq!(double(21), 42);
    }
}

use std::{env, path::PathBuf, process};

fn main() {
    println!("cargo:rerun-if-env-changed=OPENSSL_DIR");

    let Some(dir) = env::var_os("OPENSSL_DIR") else {
        eprintln!("Could not find directory of OpenSSL installation");
        eprintln!("OPENSSL_DIR is not set; set OPENSSL_DIR to the OpenSSL install root.");
        process::exit(1);
    };

    let dir = PathBuf::from(dir);
    if !dir.is_dir() {
        eprintln!("Could not find directory of OpenSSL installation: {}", dir.display());
        eprintln!("OPENSSL_DIR must point to an existing directory.");
        process::exit(1);
    }
}

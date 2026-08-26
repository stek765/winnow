// winnow, as a window.
//
// The shell owns almost nothing: it starts the Python engine, waits for it to
// say which port it took, and points a webview at it. Every decision — which
// face the home screen wears, what the button does, what a run costs — stays
// in Python, where it is tested offline.
//
// That is the whole reason this file is short. A shell that knew where the
// findings live, or when a recap is worth offering, would have to be rewritten
// the day it is replaced.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

/// The engine, so it can be killed when the window closes.
///
/// A server that outlives its window is a port held forever and a process the
/// user cannot see to stop.
struct Engine(Mutex<Option<Child>>);

/// Where `winnow` might be, when the PATH is not the shell's.
///
/// An app launched from Finder inherits a minimal PATH — usually just
/// /usr/bin:/bin:/usr/sbin:/sbin — so the pipx install in ~/.local/bin is
/// invisible to it. Looking in the usual places is the difference between an
/// app that starts and one that only works from a terminal.
fn engine_command() -> String {
    if let Some(home) = std::env::var_os("HOME") {
        let home = std::path::Path::new(&home);
        for guess in [
            ".local/bin/winnow",
            "Library/Application Support/pipx/venvs/winnow/bin/winnow",
        ] {
            let path = home.join(guess);
            if path.is_file() {
                return path.to_string_lossy().into_owned();
            }
        }
    }
    for guess in ["/opt/homebrew/bin/winnow", "/usr/local/bin/winnow"] {
        if std::path::Path::new(guess).is_file() {
            return guess.to_string();
        }
    }
    // Nothing found: let PATH try, so a terminal launch still works.
    "winnow".to_string()
}

/// Start `winnow serve` and read back the port it took.
///
/// The port is never hard-coded: a fixed one is a crash waiting for the day
/// something else already holds it, and an app must not open on a blank page
/// because of that.
fn start_engine() -> Result<(Child, u16), String> {
    let mut child = Command::new(engine_command())
        .arg("serve")
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|e| {
            format!(
                "cannot start winnow ({e}).\n\
                 Install it with:\n  \
                 pipx install git+https://github.com/stek765/winnow"
            )
        })?;

    let stdout = child.stdout.take().ok_or("engine produced no output")?;
    let mut reader = BufReader::new(stdout);
    let mut line = String::new();

    reader
        .read_line(&mut line)
        .map_err(|e| format!("cannot read the engine's port: {e}"))?;

    let port = line
        .trim()
        .strip_prefix("WINNOW_PORT=")
        .and_then(|p| p.parse::<u16>().ok())
        .ok_or_else(|| format!("the engine did not announce a port (said: {line:?})"))?;

    // Everything the engine prints after that line still has to be read.
    //
    // The first version of this comment had the reasoning backwards: it said a
    // shell that kept hold of the pipe would block the engine. The opposite is
    // true — a pipe nobody drains fills up (64 KB on macOS) and then the
    // *writer* blocks on its next print, forever. A collection prints a line
    // per post, so the engine would have frozen mid-run with the window still
    // showing a spinner, and nothing anywhere saying why.
    //
    // Forwarded rather than discarded, so `winnow.app`'s output is still
    // readable from a terminal when something goes wrong.
    std::thread::spawn(move || {
        for line in reader.lines().map_while(Result::ok) {
            println!("{line}");
        }
    });

    Ok((child, port))
}

fn main() {
    let (child, port) = match start_engine() {
        Ok(pair) => pair,
        Err(message) => {
            eprintln!("{message}");
            std::process::exit(1);
        }
    };

    // `native` tells the page it is in this window and not a browser tab, so
    // it can leave a band clear for the traffic lights drawn over its top-left
    // corner. The shell says it outright rather than letting the page guess
    // from the user agent — the same page is served to both.
    let url = format!("http://127.0.0.1:{port}/?native=mac");

    tauri::Builder::default()
        .manage(Engine(Mutex::new(Some(child))))
        .setup(move |app| {
            let parsed = url.parse().expect("the engine's URL is well formed");
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(parsed))
                .title("winnow")
                .inner_size(980.0, 680.0)
                .min_inner_size(560.0, 460.0)
                // The bar with the wheat ear is the app's own: the system one
                // on top of it would be two titles for one window.
                .title_bar_style(tauri::TitleBarStyle::Overlay)
                // Overlay only makes the title bar transparent: macOS keeps
                // drawing the window title over the page, and on this light
                // bar it reads as a white smudge next to the wheat ear.
                .hidden_title(true)
                .build()?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                // The engine dies with the window it was started for.
                if let Some(engine) = window.app_handle().try_state::<Engine>() {
                    if let Some(mut child) = engine.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("winnow failed to start");
}

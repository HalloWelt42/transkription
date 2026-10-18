import "appkern-oberflaeche/stil.css";
import "./stil/transkription.css";
import { aufnahmeEinrichten } from "appkern-oberflaeche";
import { mount } from "svelte";
import App from "./App.svelte";

// Aufnehmen im Browser: eigener Gerätespeicher, Live-Mitschrift über den Hördienst der App
aufnahmeEinrichten({ app: "transkription", hoeren: "/hoeren", name: "Sprachnotiz" });

mount(App, { target: document.getElementById("app")! });

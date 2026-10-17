import "appkern-oberflaeche/stil.css";
import "./stil/transkription.css";
import { mount } from "svelte";
import App from "./App.svelte";

mount(App, { target: document.getElementById("app")! });

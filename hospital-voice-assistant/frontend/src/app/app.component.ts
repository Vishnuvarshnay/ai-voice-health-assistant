import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ConnectionState } from 'livekit-client';
import { ApiService, IntentResult } from './services/api.service';
import { LivekitService } from './services/livekit.service';
import { environment } from '../environments/environment';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css'],
})
export class AppComponent implements OnInit {
  private api = inject(ApiService);
  livekit = inject(LivekitService);

  identity = 'patient-' + Math.floor(Math.random() * 9999);
  roomName = 'hva-' + Math.floor(Math.random() * 9999);

  connecting = signal(false);
  connected = signal(false);
  error = signal<string | null>(null);

  transcriptInput = '';
  lastIntent = signal<IntentResult | null>(null);
  classifying = signal(false);

  ngOnInit(): void {
    this.livekit.state$.subscribe((s) => {
      this.connected.set(s === ConnectionState.Connected);
    });
  }

  livekitUrl = computed(() => environment.livekitUrl);

  async joinRoom(): Promise<void> {
    this.error.set(null);
    this.connecting.set(true);
    try {
      const t = await this.api.mintToken(this.roomName, this.identity).toPromise();
      if (!t) throw new Error('Empty token response');
      await this.livekit.connect(t.url, t.token);
    } catch (e: any) {
      this.error.set(e?.message ?? 'Failed to join room');
    } finally {
      this.connecting.set(false);
    }
  }

  async leaveRoom(): Promise<void> {
    await this.livekit.disconnect();
  }

  async classifyText(): Promise<void> {
    const text = this.transcriptInput.trim();
    if (!text) return;
    this.classifying.set(true);
    this.error.set(null);
    try {
      const res = await this.api.classifyIntent(text).toPromise();
      this.lastIntent.set(res ?? null);
    } catch (e: any) {
      this.error.set(e?.message ?? 'Classification failed');
    } finally {
      this.classifying.set(false);
    }
  }

  intentJson(): string {
    const v = this.lastIntent();
    return v ? JSON.stringify(v, null, 2) : '';
  }
}

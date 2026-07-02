import { Injectable } from '@angular/core';
import {
  Room,
  RoomEvent,
  RemoteParticipant,
  RemoteTrackPublication,
  RemoteTrack,
  Track,
  ConnectionState,
  createLocalAudioTrack,
} from 'livekit-client';
import { BehaviorSubject } from 'rxjs';

export interface AgentMessage {
  role: 'agent' | 'user';
  text: string;
  ts: number;
}

@Injectable({ providedIn: 'root' })
export class LivekitService {
  private room: Room | null = null;
  readonly state$ = new BehaviorSubject<ConnectionState>(ConnectionState.Disconnected);
  readonly messages$ = new BehaviorSubject<AgentMessage[]>([]);
  readonly audioLevel$ = new BehaviorSubject<number>(0);

  async connect(url: string, token: string): Promise<void> {
    this.room = new Room({
      adaptiveStream: true,
      dynacast: true,
    });

    this.room
      .on(RoomEvent.ConnectionStateChanged, (s) => this.state$.next(s))
      .on(RoomEvent.TrackSubscribed, this.onTrackSubscribed.bind(this))
      .on(RoomEvent.ParticipantConnected, (p: RemoteParticipant) => {
        this.log('agent', `Agent "${p.identity}" joined.`);
      })
      .on(RoomEvent.DataReceived, (payload) => {
        try {
          const txt = new TextDecoder().decode(payload);
          const data = JSON.parse(txt);
          if (data.role && data.text) {
            this.log(data.role, data.text);
          }
        } catch {
          /* ignore non-json data */
        }
      })
      .on(RoomEvent.Disconnected, () => this.state$.next(ConnectionState.Disconnected));

    await this.room.connect(url, token);

    // Publish microphone.
    const mic = await createLocalAudioTrack({ echoCancellation: true, noiseSuppression: true });
    await this.room.localParticipant.publishTrack(mic);
  }

  async disconnect(): Promise<void> {
    if (this.room) {
      await this.room.disconnect();
      this.room = null;
    }
    this.state$.next(ConnectionState.Disconnected);
  }

  private onTrackSubscribed(
    track: RemoteTrack,
    _publication: RemoteTrackPublication,
    participant: RemoteParticipant
  ): void {
    if (track.kind === Track.Kind.Audio) {
      const el = track.attach();
      el.setAttribute('playsinline', 'true');
      el.autoplay = true;
      document.body.appendChild(el);
      this.log('agent', `Audio track from ${participant.identity} attached.`);
    }
  }

  private log(role: 'agent' | 'user', text: string): void {
    const list = this.messages$.value.slice();
    list.push({ role, text, ts: Date.now() });
    this.messages$.next(list.slice(-100));
  }
}

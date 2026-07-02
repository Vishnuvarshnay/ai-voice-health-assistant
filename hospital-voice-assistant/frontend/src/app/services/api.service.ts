import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface VoiceToken {
  token: string;
  url: string;
  room_name: string;
  identity: string;
}

export interface IntentResult {
  service_code: string | null;
  service_name: string | null;
  confidence: number;
  used_fallback: boolean;
  detected_language: string | null;
  normalized_transcript_en: string;
  slots: Record<string, unknown>;
  top_candidates: Array<{
    service_code: string;
    service_name: string;
    semantic_score: number;
    keyword_score: number;
    hybrid_confidence: number;
  }>;
}

export interface HospitalService {
  id: number;
  code: string;
  name: string;
  description: string;
  category_id: number;
  keywords: string[];
  required_slots: string[];
  priority: string;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private base = environment.apiBase;

  mintToken(roomName: string, identity: string): Observable<VoiceToken> {
    return this.http.post<VoiceToken>(`${this.base}/api/v1/voice/token`, {
      room_name: roomName,
      identity,
    });
  }

  classifyIntent(transcript: string): Observable<IntentResult> {
    return this.http.post<IntentResult>(`${this.base}/api/v1/intent/classify`, {
      transcript,
    });
  }

  listServices(): Observable<HospitalService[]> {
    return this.http.get<HospitalService[]>(`${this.base}/api/v1/services`);
  }
}

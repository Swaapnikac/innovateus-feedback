"use client";

import { useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { InnovateLogo } from "@/components/InnovateLogo";
import { Shield, ArrowRight, Globe, CheckCircle2, Clock } from "lucide-react";
import { api } from "@/lib/api";

const LANGUAGES = [
  { code: "en", label: "English", flag: "🇺🇸" },
  { code: "es", label: "Español", flag: "🇪🇸" },
  { code: "fr", label: "Français", flag: "🇫🇷" },
  { code: "pt", label: "Português", flag: "🇧🇷" },
  { code: "zh", label: "中文", flag: "🇨🇳" },
  { code: "hi", label: "हिन्दी", flag: "🇮🇳" },
  { code: "ar", label: "العربية", flag: "🇸🇦" },
] as const;

const UI_TEXT: Record<string, {
  title: string; subtitle: string; privacyTitle: string;
  privacy: string[]; consentLabel: string; begin: string; starting: string; timeNote: string;
}> = {
  en: {
    title: "Post-Course Feedback",
    subtitle: "Help us improve this course for future learners.",
    privacyTitle: "Your Privacy",
    timeNote: "This takes about 2–4 minutes",
    privacy: [
      "Your responses are completely anonymous",
      "No audio is stored — only transcript text is saved",
      "No identifying information is collected",
      "Responses are used only to improve the program",
    ],
    consentLabel: "I understand that my responses are anonymous and I consent to participate in this feedback survey.",
    begin: "Begin Survey",
    starting: "Starting...",
  },
  es: {
    title: "Encuesta Post-Curso",
    subtitle: "Ayúdenos a mejorar este curso para futuros participantes.",
    privacyTitle: "Su Privacidad",
    timeNote: "Esto toma aproximadamente 2–4 minutos",
    privacy: [
      "Sus respuestas son completamente anónimas",
      "No se almacena audio — solo se guarda el texto transcrito",
      "No se recopila información identificable",
      "Las respuestas se utilizan solo para mejorar el programa",
    ],
    consentLabel: "Entiendo que mis respuestas son anónimas y doy mi consentimiento para participar en esta encuesta.",
    begin: "Comenzar Encuesta",
    starting: "Iniciando...",
  },
  fr: {
    title: "Enquête Post-Formation",
    subtitle: "Aidez-nous à améliorer ce cours pour les futurs apprenants.",
    privacyTitle: "Votre Confidentialité",
    timeNote: "Cela prend environ 2 à 4 minutes",
    privacy: [
      "Vos réponses sont entièrement anonymes",
      "Aucun audio n'est stocké — seul le texte transcrit est sauvegardé",
      "Aucune information d'identification n'est collectée",
      "Les réponses sont utilisées uniquement pour améliorer le programme",
    ],
    consentLabel: "Je comprends que mes réponses sont anonymes et je consens à participer à cette enquête.",
    begin: "Commencer l'Enquête",
    starting: "Démarrage...",
  },
  pt: {
    title: "Pesquisa Pós-Curso",
    subtitle: "Ajude-nos a melhorar este curso para futuros participantes.",
    privacyTitle: "Sua Privacidade",
    timeNote: "Isso leva cerca de 2 a 4 minutos",
    privacy: [
      "Suas respostas são completamente anônimas",
      "Nenhum áudio é armazenado — apenas o texto transcrito é salvo",
      "Nenhuma informação de identificação é coletada",
      "As respostas são usadas apenas para melhorar o programa",
    ],
    consentLabel: "Eu entendo que minhas respostas são anônimas e consinto em participar desta pesquisa.",
    begin: "Iniciar Pesquisa",
    starting: "Iniciando...",
  },
  zh: {
    title: "课后反馈问卷",
    subtitle: "帮助我们为未来的学员改进课程。",
    privacyTitle: "您的隐私",
    timeNote: "大约需要2-4分钟",
    privacy: ["您的回答完全匿名", "不存储任何音频——仅保存转录文本", "不收集任何身份信息", "回答仅用于改进项目"],
    consentLabel: "我了解我的回答是匿名的，并同意参与此反馈问卷。",
    begin: "开始问卷",
    starting: "正在启动...",
  },
  hi: {
    title: "पाठ्यक्रम के बाद फीडबैक",
    subtitle: "भविष्य के शिक्षार्थियों के लिए इस पाठ्यक्रम को बेहतर बनाने में हमारी मदद करें।",
    privacyTitle: "आपकी गोपनीयता",
    timeNote: "इसमें लगभग 2-4 मिनट लगेंगे",
    privacy: ["आपके उत्तर पूरी तरह से गुमनाम हैं", "कोई ऑडियो संग्रहीत नहीं किया जाता", "कोई पहचान संबंधी जानकारी एकत्र नहीं की जाती", "उत्तरों का उपयोग केवल कार्यक्रम को बेहतर बनाने के लिए किया जाता है"],
    consentLabel: "मैं समझता/समझती हूं कि मेरे उत्तर गुमनाम हैं और मैं इस सर्वेक्षण में भाग लेने के लिए सहमति देता/देती हूं।",
    begin: "सर्वेक्षण शुरू करें",
    starting: "शुरू हो रहा है...",
  },
  ar: {
    title: "استبيان ما بعد الدورة",
    subtitle: "ساعدنا في تحسين هذه الدورة للمتعلمين في المستقبل.",
    privacyTitle: "خصوصيتك",
    timeNote: "يستغرق هذا حوالي 2-4 دقائق",
    privacy: ["ردودك مجهولة تمامًا", "لا يتم تخزين أي صوت", "لا يتم جمع أي معلومات تعريفية", "تُستخدم الردود فقط لتحسين البرنامج"],
    consentLabel: "أفهم أن ردودي مجهولة وأوافق على المشاركة في هذا الاستبيان.",
    begin: "ابدأ الاستبيان",
    starting: "جارٍ البدء...",
  },
};

export default function ConsentPage() {
  const router = useRouter();
  const params = useParams();
  const cohortId = params.cohortId as string;
  const [agreed, setAgreed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [language, setLanguage] = useState("en");

  const t = UI_TEXT[language] || UI_TEXT.en;
  const isRTL = language === "ar";

  const handleStart = async () => {
    setLoading(true);
    try {
      const { submission_id } = await api.startSubmission(cohortId, language);
      sessionStorage.setItem("submission_id", submission_id);
      sessionStorage.setItem("survey_language", language);
      router.push(`/c/${cohortId}/survey`);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to start survey");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-brand-light-blue/40" dir={isRTL ? "rtl" : "ltr"}>
      {/* Header */}
      <header className="bg-white/60 backdrop-blur-sm border-b border-brand-blue/5 px-6 py-4">
        <div className="max-w-2xl mx-auto">
          <InnovateLogo size="sm" className="text-brand-blue" />
        </div>
      </header>

      <div className="max-w-lg mx-auto px-4 py-10 space-y-6">
        {/* Title Card */}
        <div className="text-center space-y-3">
          <div className="inline-flex items-center gap-2 bg-brand-yellow/15 text-brand-dark-yellow text-xs font-semibold uppercase tracking-widest px-4 py-1.5 rounded-full">
            <Clock className="h-3 w-3" />
            {t.timeNote}
          </div>
          <h1 className="text-3xl font-serif text-brand-blue">{t.title}</h1>
          <p className="text-brand-blue/60">{t.subtitle}</p>
        </div>

        {/* Language Picker */}
        <Card className="bg-white border-0 shadow-sm rounded-2xl">
          <CardContent className="pt-5 pb-4">
            <div className="flex items-center gap-2 text-xs font-semibold text-brand-blue/40 uppercase tracking-widest mb-3">
              <Globe className="h-3.5 w-3.5" />
              Language
            </div>
            <div className="flex flex-wrap gap-2">
              {LANGUAGES.map((lang) => (
                <button
                  key={lang.code}
                  onClick={() => setLanguage(lang.code)}
                  className={`px-3 py-1.5 rounded-full text-sm transition-all ${
                    language === lang.code
                      ? "bg-brand-blue text-white shadow-sm"
                      : "bg-brand-light-blue/60 text-brand-blue/70 hover:bg-brand-light-blue"
                  }`}
                >
                  {lang.flag} {lang.label}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Privacy Card */}
        <Card className="bg-white border-0 shadow-sm rounded-2xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-brand-blue flex items-center gap-2">
              <Shield className="h-4 w-4 text-brand-teal" />
              {t.privacyTitle}
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <ul className="space-y-2.5">
              {t.privacy.map((item, i) => (
                <li key={i} className="flex items-start gap-2.5 text-sm text-brand-blue/60">
                  <CheckCircle2 className="h-4 w-4 text-brand-teal shrink-0 mt-0.5" />
                  {item}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        {/* Consent + Start */}
        <Card className="bg-white border-0 shadow-sm rounded-2xl">
          <CardContent className="pt-5 space-y-5">
            <label className="flex items-start gap-3 cursor-pointer">
              <Checkbox
                checked={agreed}
                onCheckedChange={(checked) => setAgreed(checked === true)}
                className="mt-0.5"
              />
              <span className="text-sm leading-relaxed text-brand-blue/70">
                {t.consentLabel}
              </span>
            </label>

            <Button
              onClick={handleStart}
              disabled={!agreed || loading}
              className="w-full h-12 text-base rounded-full bg-brand-blue hover:bg-brand-blue/90 gap-2 shadow-md hover:shadow-lg transition-all"
            >
              {loading ? t.starting : t.begin}
              <ArrowRight className="h-4 w-4" />
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

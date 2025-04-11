# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from typing import Tuple

from ovos_bus_client.session import SessionManager, Session
from ovos_utils import classproperty
from ovos_utils.gui import can_use_gui
from ovos_utils.log import LOG
from ovos_utils.process_utils import RuntimeRequirements
from ovos_wikipedia_solver import WikipediaSolver
from ovos_workshop.decorators import intent_handler, common_query
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills.ovos import OVOSSkill


class WikipediaSkill(OVOSSkill):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session_results = {}
        self.wiki = WikipediaSolver(translator=self.translator,
                                    detector=self.lang_detector)

    @classproperty
    def runtime_requirements(self):
        """ indicate to OVOS this skill should ONLY
         be loaded if we have internet connection"""
        return RuntimeRequirements(
            internet_before_load=True,
            network_before_load=True,
            gui_before_load=False,
            requires_internet=True,
            requires_network=True,
            requires_gui=False,
            no_internet_fallback=False,
            no_network_fallback=False,
            no_gui_fallback=True,
        )

    # intents
    @intent_handler("wiki.intent",
                    voc_blacklist=["Weather", "Help"])
    def handle_search(self, message):
        """Extract what the user asked about and reply with info
        from wikipedia.
        """
        query = message.data["query"]

        sess = SessionManager.get(message)
        self.session_results[sess.session_id] = {
            "query": query,
            "results": [],
            "idx": 0,
            "lang": sess.lang,
            "image": None,
        }

        self.gui.show_animated_image("jumping.gif")

        self.speak_dialog("searching", {"query": query})

        title, summary = self.ask_the_wiki(sess)
        if summary:
            self.speak_result(sess)
        else:
            self.speak_dialog("no_answer")

    # @intent_handler("wikiroulette.intent")
    # def handle_wiki_roulette_query(self, message):
    #    """Random wikipedia page"""
    #    self.gui.show_animated_image(join(dirname(__file__), "ui", "jumping.gif"))
    #    self.speak_dialog("wikiroulette")
    # TODO

    @intent_handler(IntentBuilder("WikiMore").require("More").require("WikiKnows"))
    def handle_tell_more(self, message):
        """Follow up query handler, "tell me more".

        If a "WikiKnows" entry exists in the active contexts
        this can be triggered.
        """
        sess = SessionManager.get(message)
        self.speak_result(sess)

    # common query
    def cq_callback(self, utterance: str, answer: str, lang: str):
        """ If selected show gui """
        sess = SessionManager.get()
        if sess.session_id in self.session_results:
            self.display_wiki_entry()
        else:
            LOG.error(f"{sess.session_id} not in "
                      f"{list(self.session_results.keys())}")
        self.set_context("WikiKnows", utterance)
        # cache long answer for "tell me more"
        self.ask_the_wiki(sess)
        self.session_results[sess.session_id]["idx"] += 1  # spoken by common query
        self.session_results[sess.session_id]["title"] = utterance

    @common_query(callback=cq_callback)
    def match_common_query(self, phrase: str, lang: str) -> Tuple[str, float]:

        if (self.voc_match(phrase, "MiscBlacklist") or
                self.voc_match(phrase, "Weather")):
            return None

        sess = SessionManager.get()
        query = self.wiki.extract_keyword(phrase, lang=lang)
        if not query:
            # doesnt look like a question we can answer at all
            return None

        self.session_results[sess.session_id] = {
            "query": query,
            "results": [],
            "idx": 0,
            "lang": lang,
            "title": phrase,
            "image": None
        }
        summary = self.wiki.get_spoken_answer(query, lang=sess.lang, units=sess.system_unit)
        if summary:
            self.log.info(f"Wikipedia answer: {summary}")
            return summary, 0.6

    # wikipedia
    def ask_the_wiki(self, sess: Session):
        query = self.session_results[sess.session_id]["query"]

        try:
            results = self.wiki.long_answer(query, lang=sess.lang, units=sess.system_unit)
        except Exception as err:  # handle solver plugin failures, happens in some queries
            self.log.error(err)
            results = None

        self.session_results[sess.session_id]["results"] = results

        if results:
            title = results[0].get("title") or \
                    self.session_results[sess.session_id]["query"]
            self.session_results[sess.session_id]["image"] = results[0].get("img")
            return title, results[0]["summary"]
        return None, None

    def display_wiki_entry(self):
        if not can_use_gui(self.bus):
            LOG.debug(f"GUI not enabled")
            return
        sess = SessionManager.get()
        image = self.session_results[sess.session_id].get("image") or \
                self.wiki.get_image(self.session_results[sess.session_id]["query"],
                                    lang=sess.lang, units=sess.system_unit)
        title = self.session_results[sess.session_id].get("title") or "Wikipedia"
        if image:
            self.session_results[sess.session_id]["image"] = image
            self.gui.show_image(image, title=title, fill='PreserveAspectFit',
                                override_idle=20, override_animations=True)
        else:
            LOG.info(f"No image in {self.session_results[sess.session_id]}")

    def speak_result(self, sess: Session):

        if sess.session_id in self.session_results:
            results = self.session_results[sess.session_id]["results"]
            idx = self.session_results[sess.session_id]["idx"]
            title = self.session_results[sess.session_id].get("title") or \
                    "Wikipedia"

            if idx + 1 > len(self.session_results):
                self.speak_dialog("thats all")
                self.remove_context("WikiKnows")
                self.session_results[sess.session_id]["idx"] = 0
            else:
                self.speak(results[idx]["summary"])
                self.set_context("WikiKnows", "wikipedia")
                self.display_wiki_entry()
                self.session_results[sess.session_id]["idx"] += 1
        else:
            self.speak_dialog("thats all")

    def stop(self):
        self.gui.release()

    def stop_session(self, sess):
        if sess.session_id in self.session_results:
            self.session_results.pop(sess.session_id)


if __name__ == "__main__":
    LOG.set_level("ERROR")
    from ovos_utils.fakebus import FakeBus

    s = WikipediaSkill(bus=FakeBus(), skill_id="wiki.skill")
    print(s.wiki.get_spoken_answer("quem é Elon Musk", "pt"))
    # ('who is Elon Musk', <CQSMatchLevel.GENERAL: 3>, 'The Musk family is a wealthy family of South African origin that is largely active in the United States and Canada.',
    # {'query': 'who is Elon Musk', 'image': None, 'title': 'Musk Family',
    # 'answer': 'The Musk family is a wealthy family of South African origin that is largely active in the United States and Canada.'})

    query = "who is Isaac Newton"
    print(s.wiki.extract_keyword(query, "en-us"))
    assert s.wiki.extract_keyword(query, "en-us") == "Isaac Newton"

    print(s.wiki.get_spoken_answer("venus", "en"))
    print(s.wiki.get_spoken_answer("elon musk", "en"))
    print(s.wiki.get_spoken_answer("mercury", "en"))

    exit()
    # full answer
    ans = s.wiki.spoken_answer(query)
    print(ans)
    # Sir Isaac Newton  (25 December 1642 – 20 March 1726/27) was an English mathematician, physicist, astronomer, alchemist, theologian, and author (described in his time as a "natural philosopher") widely recognised as one of the greatest mathematicians and physicists of all time and among the most influential scientists. He was a key figure in the philosophical revolution known as the Enlightenment. His book Philosophiæ Naturalis Principia Mathematica (Mathematical Principles of Natural Philosophy), first published in 1687, established classical mechanics. Newton also made seminal contributions to optics, and shares credit with German mathematician Gottfried Wilhelm Leibniz for developing infinitesimal calculus.
    # In the Principia, Newton formulated the laws of motion and universal gravitation that formed the dominant scientific viewpoint until it was superseded by the theory of relativity. Newton used his mathematical description of gravity to derive Kepler's laws of planetary motion, account for tides, the trajectories of comets, the precession of the equinoxes and other phenomena, eradicating doubt about the Solar System's heliocentricity. He demonstrated that the motion of objects on Earth and celestial bodies could be accounted for by the same principles. Newton's inference that the Earth is an oblate spheroid was later confirmed by the geodetic measurements of Maupertuis, La Condamine, and others, convincing most European scientists of the superiority of Newtonian mechanics over earlier systems.
    # Newton built the first practical reflecting telescope and developed a sophisticated theory of colour based on the observation that a prism separates white light into the colours of the visible spectrum. His work on light was collected in his highly influential book Opticks, published in 1704. He also formulated an empirical law of cooling, made the first theoretical calculation of the speed of sound, and introduced the notion of a Newtonian fluid. In addition to his work on calculus, as a mathematician Newton contributed to the study of power series, generalised the binomial theorem to non-integer exponents, developed a method for approximating the roots of a function, and classified most of the cubic plane curves.
    # Newton was a fellow of Trinity College and the second Lucasian Professor of Mathematics at the University of Cambridge. He was a devout but unorthodox Christian who privately rejected the doctrine of the Trinity. He refused to take holy orders in the Church of England unlike most members of the Cambridge faculty of the day. Beyond his work on the mathematical sciences, Newton dedicated much of his time to the study of alchemy and biblical chronology, but most of his work in those areas remained unpublished until long after his death. Politically and personally tied to the Whig party, Newton served two brief terms as Member of Parliament for the University of Cambridge, in 1689–1690 and 1701–1702. He was knighted by Queen Anne in 1705 and spent the last three decades of his life in London, serving as Warden (1696–1699) and Master (1699–1727) of the Royal Mint, as well as president of the Royal Society (1703–1727).

    query = "venus"
    # chunked answer, "tell me more"
    for sentence in s.wiki.long_answer(query):
        print(sentence["title"])
        print(sentence["summary"])
        print(sentence.get("img"))

        # who is Isaac Newton
        # Sir Isaac Newton  (25 December 1642 – 20 March 1726/27) was an English mathematician, physicist, astronomer, alchemist, theologian, and author (described in his time as a "natural philosopher") widely recognised as one of the greatest mathematicians and physicists of all time and among the most influential scientists.
        # https://upload.wikimedia.org/wikipedia/commons/3/3b/Portrait_of_Sir_Isaac_Newton%2C_1689.jpg

        # who is Isaac Newton
        # He was a key figure in the philosophical revolution known as the Enlightenment.
        # https://upload.wikimedia.org/wikipedia/commons/3/3b/Portrait_of_Sir_Isaac_Newton%2C_1689.jpg

        # who is Isaac Newton
        # His book Philosophiæ Naturalis Principia Mathematica (Mathematical Principles of Natural Philosophy), first published in 1687, established classical mechanics.
        # https://upload.wikimedia.org/wikipedia/commons/3/3b/Portrait_of_Sir_Isaac_Newton%2C_1689.jpg

        # who is Isaac Newton
        # Newton also made seminal contributions to optics, and shares credit with German mathematician Gottfried Wilhelm Leibniz for developing infinitesimal calculus.
        # In the Principia, Newton formulated the laws of motion and universal gravitation that formed the dominant scientific viewpoint until it was superseded by the theory of relativity.
        # https://upload.wikimedia.org/wikipedia/commons/3/3b/Portrait_of_Sir_Isaac_Newton%2C_1689.jpg

        # who is Isaac Newton
        # Newton used his mathematical description of gravity to derive Kepler's laws of planetary motion, account for tides, the trajectories of comets, the precession of the equinoxes and other phenomena, eradicating doubt about the Solar System's heliocentricity.
        # https://upload.wikimedia.org/wikipedia/commons/3/3b/Portrait_of_Sir_Isaac_Newton%2C_1689.jpg

        # who is Isaac Newton
        # He demonstrated that the motion of objects on Earth and celestial bodies could be accounted for by the same principles.
        # https://upload.wikimedia.org/wikipedia/commons/3/3b/Portrait_of_Sir_Isaac_Newton%2C_1689.jpg

        # who is Isaac Newton
        # Newton's inference that the Earth is an oblate spheroid was later confirmed by the geodetic measurements of Maupertuis, La Condamine, and others, convincing most European scientists of the superiority of Newtonian mechanics over earlier systems.
        # Newton built the first practical reflecting telescope and developed a sophisticated theory of colour based on the observation that a prism separates white light into the colours of the visible spectrum.
        # https://upload.wikimedia.org/wikipedia/commons/3/3b/Portrait_of_Sir_Isaac_Newton%2C_1689.jpg

        # who is Isaac Newton
        # His work on light was collected in his highly influential book Opticks, published in 1704.
        # https://upload.wikimedia.org/wikipedia/commons/3/3b/Portrait_of_Sir_Isaac_Newton%2C_1689.jpg

        # who is Isaac Newton
        # He also formulated an empirical law of cooling, made the first theoretical calculation of the speed of sound, and introduced the notion of a Newtonian fluid.
        # https://upload.wikimedia.org/wikipedia/commons/3/3b/Portrait_of_Sir_Isaac_Newton%2C_1689.jpg

        # who is Isaac Newton
        # In addition to his work on calculus, as a mathematician Newton contributed to the study of power series, generalised the binomial theorem to non-integer exponents, developed a method for approximating the roots of a function, and classified most of the cubic plane curves.
        # Newton was a fellow of Trinity College and the second Lucasian Professor of Mathematics at the University of Cambridge.
        # https://upload.wikimedia.org/wikipedia/commons/3/3b/Portrait_of_Sir_Isaac_Newton%2C_1689.jpg

        # who is Isaac Newton
        # He was a devout but unorthodox Christian who privately rejected the doctrine of the Trinity.
        # https://upload.wikimedia.org/wikipedia/commons/3/3b/Portrait_of_Sir_Isaac_Newton%2C_1689.jpg

        # who is Isaac Newton
        # He refused to take holy orders in the Church of England unlike most members of the Cambridge faculty of the day.
        # https://upload.wikimedia.org/wikipedia/commons/3/3b/Portrait_of_Sir_Isaac_Newton%2C_1689.jpg

        # who is Isaac Newton
        # Beyond his work on the mathematical sciences, Newton dedicated much of his time to the study of alchemy and biblical chronology, but most of his work in those areas remained unpublished until long after his death.
        # https://upload.wikimedia.org/wikipedia/commons/3/3b/Portrait_of_Sir_Isaac_Newton%2C_1689.jpg

        # who is Isaac Newton
        # Politically and personally tied to the Whig party, Newton served two brief terms as Member of Parliament for the University of Cambridge, in 1689–1690 and 1701–1702.
        # https://upload.wikimedia.org/wikipedia/commons/3/3b/Portrait_of_Sir_Isaac_Newton%2C_1689.jpg

    # lang support
    query = "Quem é Isaac Newton"
    sentence = s.wiki.spoken_answer(query, context={"lang": "pt"})
    assert s.wiki.extract_keyword(query, "pt") == "Isaac Newton"
    print(sentence)
    # Sir Isaac Newton (25 de dezembro de 1642 - 20 de março de 1726/27) foi um matemático, físico, astrônomo, alquimista, teólogo e autor (descrito em seu tempo como um "filósofo natural") amplamente reconhecido como um dos maiores matemáticos e físicos de todos os tempos e entre os cientistas mais influentes. Ele era uma figura chave na revolução filosófica conhecida como Iluminismo. Seu livro Philosophiæ Naturalis Principia Mathematica (Princípios matemáticos da Filosofia Natural), publicado pela primeira vez em 1687, estabeleceu a mecânica clássica. Newton também fez contribuições seminais para a óptica, e compartilha crédito com o matemático alemão Gottfried Wilhelm Leibniz para desenvolver cálculo infinitesimal.
    # No Principia, Newton formulou as leis do movimento e da gravitação universal que formaram o ponto de vista científico dominante até ser superado pela teoria da relatividade. Newton usou sua descrição matemática da gravidade para derivar as leis de Kepler do movimento planetário, conta para as marés, as trajetórias dos cometas, a precessão dos equinócios e outros fenômenos, erradicando dúvidas sobre a heliocentricidade do Sistema Solar. Ele demonstrou que o movimento de objetos na Terra e corpos celestes poderia ser contabilizado pelos mesmos princípios. A inferência de Newton de que a Terra é um esferóide oblate foi mais tarde confirmada pelas medidas geodésicas de Maupertuis, La Condamine, e outros, convencendo a maioria dos cientistas europeus da superioridade da mecânica newtoniana sobre sistemas anteriores.
    # Newton construiu o primeiro telescópio reflexivo prático e desenvolveu uma teoria sofisticada da cor baseada na observação de que um prisma separa a luz branca nas cores do espectro visível. Seu trabalho sobre luz foi coletado em seu livro altamente influente Opticks, publicado em 1704. Ele também formulou uma lei empírica de resfriamento, fez o primeiro cálculo teórico da velocidade do som e introduziu a noção de um fluido Newtoniano. Além de seu trabalho em cálculo, como um matemático Newton contribuiu para o estudo da série de energia, generalizou o teorema binomial para expoentes não inteiros, desenvolveu um método para aproximar as raízes de uma função e classificou a maioria das curvas de plano cúbico.
    # Newton era um companheiro do Trinity College e o segundo professor Lucasian de Matemática na Universidade de Cambridge. Ele era um cristão devoto, mas não ortodoxo, que rejeitou privadamente a doutrina da Trindade. Ele se recusou a tomar ordens sagradas na Igreja da Inglaterra, ao contrário da maioria dos membros da faculdade de Cambridge do dia. Além de seu trabalho nas ciências matemáticas, Newton dedicou grande parte de seu tempo ao estudo da alquimia e da cronologia bíblica, mas a maioria de seu trabalho nessas áreas permaneceu inédita até muito tempo depois de sua morte. Politicamente e pessoalmente ligado ao partido Whig, Newton serviu dois mandatos breves como membro do Parlamento para a Universidade de Cambridge, em 1689-1690 e 1701-1702. Ele foi condecorado pela rainha Anne em 1705 e passou as últimas três décadas de sua vida em Londres, servindo como Warden (1696-1699) e Master (1699–1727) da Royal Mint, bem como presidente da Royal Society (1703–1727)

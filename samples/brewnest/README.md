# Brewnest test kit

A fictional brand for trying AdGenius end to end. Brewnest sells canned cold brew coffee in India.

## 1. Create the brand

Brands -> New brand

| Field | Value |
|---|---|
| Brand name | Brewnest |
| Industry | Ready-to-drink coffee |

Then fill in the profile and click **Save profile**:

| Field | Value |
|---|---|
| Description | Ready-to-drink cold brew coffee in cans, slow-brewed for 18 hours in Bengaluru. |
| Brand voice | Smart, warm and quietly confident; playful but never sarcastic |
| Target audience | Students and young professionals aged 19-28 in Indian cities |
| Restriction 1 | Never say 'healthy', 'guilt-free' or 'boosts immunity' |
| Restriction 2 | Never show people drinking Brewnest while driving |
| Competitors | Add two rows: Sleepy Owl, Starbucks Doubleshot (used for web research) |
| Brand colours | Nest Brown #4A2C21, Cream #F3E9DC, Signal Orange #FF7A1A |

## 2. Upload the documents (Knowledge base tab)

| File | Document type | Tests |
|---|---|---|
| brewnest_brand_guidelines.pdf | Brand guidelines | PDF extraction |
| brewnest_legal_compliance.docx | Other | Word extraction |
| brewnest_products.csv | Product catalogue | CSV rows as text |
| brewnest_customer_personas.txt | Customer persona | Plain text |
| invalid/not_really_a_pdf.pdf | (any) | Should be **rejected**: the content doesn't match the extension |

All four valid files should reach **Indexed** within a minute.

## 3. Ask the knowledge base (brand page)

Each of these questions has a definite answer in the documents, so you can check the
answer and its citations:

| Question | Expected answer | Source |
|---|---|---|
| What is Brewnest's tagline? | "Brewed slow. Lived fast." (end of every video ad) | guidelines PDF |
| How much caffeine is in Vanilla Oat? | 140 mg per 250 ml can | products CSV |
| What caffeine disclaimer must ads show? | "Contains caffeine. Not recommended for children, pregnant women or persons sensitive to caffeine." | legal DOCX |
| What is the price of Mango Tonic? | Rs 150 | CSV + DOCX |
| Why do people first try Brewnest? | 71% because a friend shared a can | personas TXT |
| What is the primary brand colour? | Nest Brown #4A2C21 | guidelines PDF |
| Who is the CEO? | Should say it **doesn't know**: not in the documents | (none) |

## 4. Create a campaign (Campaigns -> New campaign)

**Step 1 - Brand & goal**
- Brand: Brewnest
- Campaign name: Mango Tonic Summer Launch
- Objective: Launch the limited-edition Mango Tonic and get students to try it this summer
- Marketing objective: Trial - 50,000 cans sold in the first 6 weeks
- Product description: Brewnest Mango Tonic - cold brew with mango and sparkling tonic, 250 ml can, Rs 150

**Step 2 - Audience & format**
- Target audience: College students aged 19-23 in Bengaluru, Pune and Hyderabad
- Platform: instagram · Format: 9:16 · Duration: 30 seconds · Language: English
- Tone: Playful, sunny, a little cheeky

**Step 3 - Creative options**
- Concepts: 3 · Budget: Rs 8 lakh
- Additional requirements: Show friends sharing cans; end on the tagline; include the caffeine disclaimer
- Competitor research: on · Competitor focus: summer coffee drinks for students

**Step 4 - Review** -> Create & generate

### What to check
- The agents should use facts from your documents: the Rs 150 price, the tagline, the
  caffeine disclaimer, the "friend shared a can" insight.
- No banned words ("healthy", "guilt-free", ...). The Critic's Evaluation tab flags any
  that slip through.
- Nobody drinks while driving; no competitor is named in the script.
- Try **Reject** on the first concepts with feedback such as "more about sharing with
  friends" and check the new concepts follow it.
